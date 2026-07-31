"""Read-only QuickBooks Online production connector for the Chief of Staff API."""

from __future__ import annotations

import base64
import os
import threading
import time
from collections.abc import Callable, Sequence
from contextlib import contextmanager
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import quote

import httpx

from app.connectors.base import BaseConnector
from app.connectors.models import ConnectorHealth, ConnectorStatus, SyncResult
from app.connectors.quickbooks_credentials import (
    QuickBooksCredentialError,
    QuickBooksCredentialStore,
)

EXPECTED_COMPANY_NAME = "MOR LOGISTICS MANITOBA LIMITED"
TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
REVOKE_URL = "https://developer.api.intuit.com/v2/oauth2/tokens/revoke"
API_BASE_URL = "https://quickbooks.api.intuit.com"
SANDBOX_API_BASE_URL = "https://sandbox-quickbooks.api.intuit.com"
MINOR_VERSION = "75"
MAX_QUERY_RESULTS = 1000

RESOURCE_ENTITY: dict[str, str] = {
    "customers": "Customer",
    "vendors": "Vendor",
    "accounts": "Account",
    "items": "Item",
    "invoices": "Invoice",
    "payments": "Payment",
    "bills": "Bill",
    "purchases": "Purchase",
    "journal_entries": "JournalEntry",
}

REPORT_NAMES: dict[str, str] = {
    "profit_loss": "ProfitAndLoss",
    "balance_sheet": "BalanceSheet",
    "cash_flow": "CashFlow",
    "aged_receivables": "AgedReceivables",
    "aged_payables": "AgedPayables",
}

_REAUTH_CODES = {400, 401, 403}
_ORG_LOCKS: dict[str, threading.Lock] = {}
_ORG_LOCKS_GUARD = threading.Lock()


class QuickBooksConnectorError(RuntimeError):
    """Safe connector error that never contains OAuth credential values."""

    def __init__(
        self,
        message: str,
        *,
        status: ConnectorStatus = ConnectorStatus.DEGRADED,
        retryable: bool = False,
    ) -> None:
        super().__init__(_redact(message))
        self.status = status
        self.retryable = retryable


class QuickBooksConnector(BaseConnector):
    """Verify and synchronize a read-only QuickBooks Online company connection."""

    def __init__(
        self,
        *,
        http_client: httpx.Client | None = None,
        now: Callable[[], float] = time.time,
        credential_store: QuickBooksCredentialStore | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        super().__init__(name="quickbooks")
        self._client = http_client
        self._owns_client = http_client is None
        self._now = now
        self._sleep = sleep
        self._credential_store = credential_store
        self._access_token: str | None = None
        self._access_token_expires_at = 0.0
        self._realm_id: str | None = None
        self._last_sync_at: datetime | None = None
        self._company_name: str | None = None
        self._refresh_lock = threading.Lock()

    def validate_configuration(self) -> None:
        missing = [
            name
            for name in (
                "POLARIS_QBO_CLIENT_ID",
                "POLARIS_QBO_CLIENT_SECRET",
                "POLARIS_QBO_TOKEN_ENCRYPTION_KEY",
            )
            if not os.getenv(name)
        ]
        if missing:
            raise QuickBooksConnectorError(
                "QuickBooks is not configured. Missing environment variables: "
                + ", ".join(missing),
                status=ConnectorStatus.NOT_CONFIGURED,
            )
        if self._mode() == "sandbox" and os.getenv("POLARIS_ENV", "development") not in {"development", "test"}:
            raise QuickBooksConnectorError(
                "QuickBooks sandbox mode is allowed only in development or test",
                status=ConnectorStatus.CONFIGURATION_ERROR,
            )
        try:
            credential = self._store().load_credential()
        except QuickBooksCredentialError as exc:
            raise QuickBooksConnectorError(str(exc), status=ConnectorStatus.AUTHORIZATION_REQUIRED) from exc
        self._realm_id = credential.realm_id

    def authenticate(self) -> None:
        self.validate_configuration()
        if self._access_token and self._now() < self._access_token_expires_at - 60:
            return
        with self._refresh_lock:
            if self._access_token and self._now() < self._access_token_expires_at - 60:
                return
            self._refresh_access_token()

    def health(self) -> ConnectorHealth:
        started = datetime.now(timezone.utc)
        store = self._store_or_none()
        try:
            verification = self.verify_company_identity()
        except QuickBooksConnectorError as exc:
            if store is not None:
                store.record_sync_failure(str(exc), status=exc.status.value)
            return ConnectorHealth(
                name=self.name,
                status=exc.status,
                message=str(exc),
                details=self.safe_status(include_resources=False),
            )

        latency_ms = (datetime.now(timezone.utc) - started).total_seconds() * 1000
        return ConnectorHealth(
            name=self.name,
            status=ConnectorStatus.HEALTHY,
            checked_at=datetime.now(timezone.utc),
            latency_ms=round(latency_ms, 2),
            last_sync_at=self._last_sync_at,
            message=f"Connected to {verification['verified_company_name']}.",
            details=self.safe_status(include_resources=True),
        )

    def discover(self) -> Sequence[str]:
        return ("company", *RESOURCE_ENTITY.keys(), *REPORT_NAMES.keys())

    def sync(self) -> SyncResult:
        started_at = datetime.now(timezone.utc)
        errors: list[str] = []
        records_read = 0
        try:
            verification = self.production_verification(max_pages_per_resource=1)
            if verification["identity_verification_status"] != "healthy":
                raise QuickBooksConnectorError(
                    "QuickBooks company identity verification failed",
                    status=ConnectorStatus.COMPANY_MISMATCH,
                )
            records_read = sum(int(value) for value in verification["record_counts"].values())
            self._last_sync_at = datetime.now(timezone.utc)
        except QuickBooksConnectorError as exc:
            errors.append(str(exc))

        return SyncResult(
            connector=self.name,
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
            records_read=records_read,
            records_written=0,
            events_published=0,
            success=not errors,
            errors=errors,
        )

    def disconnect(self, *, revoke: bool = False) -> None:
        if revoke:
            try:
                credential = self._store().load_credential()
                self._revoke_token(credential.refresh_token)
            except QuickBooksConnectorError:
                raise
            except Exception as exc:
                raise QuickBooksConnectorError(
                    "QuickBooks token revocation failed",
                    status=ConnectorStatus.DEGRADED,
                ) from exc
        self._access_token = None
        self._access_token_expires_at = 0.0
        self._realm_id = None

    def company_info(self) -> dict[str, Any]:
        payload = self._get(
            f"companyinfo/{self._require_realm_id()}",
            operation="company information",
        )
        company = payload.get("CompanyInfo")
        if not isinstance(company, dict):
            raise QuickBooksConnectorError("QuickBooks company information was not returned")
        return _decimal_safe(company)

    def verify_company_identity(self) -> dict[str, Any]:
        company = self.company_info()
        company_name = str(company.get("CompanyName") or company.get("LegalName") or "")
        expected = expected_company_name()
        if _normalize_company_name(company_name) != _normalize_company_name(expected):
            message = "QuickBooks company identity does not match the configured organization."
            self._store().record_verification(status="company_mismatch", company_name=None, error_summary=message)
            raise QuickBooksConnectorError(message, status=ConnectorStatus.COMPANY_MISMATCH)
        self._company_name = company_name.strip()
        self._store().record_verification(status="healthy", company_name=self._company_name)
        return {
            "expected_company_name": expected,
            "verified_company_name": self._company_name,
            "identity_verification_status": "healthy",
            "verified_at": datetime.now(timezone.utc).isoformat(),
        }

    def accounts(self) -> list[dict[str, Any]]:
        return self.list_resource("accounts", order_by="FullyQualifiedName")

    def list_resource(
        self,
        resource: str,
        *,
        changed_since: datetime | str | None = None,
        cursor: int | str | None = None,
        limit: int = 100,
        order_by: str | None = None,
    ) -> list[dict[str, Any]]:
        page, _next_cursor = self.list_resource_page(
            resource,
            changed_since=changed_since,
            cursor=cursor,
            limit=limit,
            order_by=order_by,
        )
        return page

    def list_resource_page(
        self,
        resource: str,
        *,
        changed_since: datetime | str | None = None,
        cursor: int | str | None = None,
        limit: int = 100,
        order_by: str | None = None,
    ) -> tuple[list[dict[str, Any]], int | None]:
        if resource not in RESOURCE_ENTITY:
            raise QuickBooksConnectorError(f"Unsupported QuickBooks resource: {resource}")
        entity = RESOURCE_ENTITY[resource]
        start_position = _parse_cursor(cursor)
        page_size = min(max(int(limit), 1), MAX_QUERY_RESULTS)
        where = ""
        if changed_since:
            value = changed_since.isoformat() if isinstance(changed_since, datetime) else str(changed_since)
            where = f" where MetaData.LastUpdatedTime > '{_escape_query_literal(value)}'"
        order = f" order by {order_by}" if order_by else ""
        query = f"select * from {entity}{where}{order} startposition {start_position} maxresults {page_size}"
        payload = self._get("query", operation=f"{resource} query", params={"query": query})
        query_response = payload.get("QueryResponse")
        if not isinstance(query_response, dict):
            raise QuickBooksConnectorError(f"QuickBooks {resource} response was malformed")
        records = query_response.get(entity, [])
        if records is None:
            records = []
        if not isinstance(records, list):
            raise QuickBooksConnectorError(f"QuickBooks {resource} were not returned as a list")
        safe_records = [_decimal_safe(record) for record in records if isinstance(record, dict)]
        next_cursor = start_position + page_size if len(safe_records) == page_size else None
        return safe_records, next_cursor

    def list_all_resource(
        self,
        resource: str,
        *,
        changed_since: datetime | str | None = None,
        limit: int = 100,
        max_pages: int = 1000,
    ) -> list[dict[str, Any]]:
        cursor: int | None = None
        records: list[dict[str, Any]] = []
        pages = 0
        while True:
            page, cursor = self.list_resource_page(
                resource,
                changed_since=changed_since,
                cursor=cursor,
                limit=limit,
            )
            records.extend(page)
            pages += 1
            if cursor is None:
                return records
            if pages >= max_pages:
                raise QuickBooksConnectorError(
                    f"QuickBooks {resource} pagination limit reached",
                    status=ConnectorStatus.DEGRADED,
                )

    def report(
        self,
        report_name: str,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
        accounting_method: str = "Accrual",
    ) -> dict[str, Any]:
        if report_name not in REPORT_NAMES and report_name not in REPORT_NAMES.values():
            raise QuickBooksConnectorError(f"Unsupported QuickBooks report: {report_name}")
        provider_report = REPORT_NAMES.get(report_name, report_name)
        if start_date and end_date and start_date > end_date:
            raise QuickBooksConnectorError("QuickBooks report start date must not exceed end date")
        method = accounting_method.title()
        if method not in {"Accrual", "Cash"}:
            raise QuickBooksConnectorError("QuickBooks accounting method must be Accrual or Cash")

        params: dict[str, str] = {"accounting_method": method}
        if start_date:
            params["start_date"] = start_date.isoformat()
        if end_date:
            params["end_date"] = end_date.isoformat()
        payload = self._get(
            f"reports/{quote(provider_report, safe='')}",
            operation=f"{provider_report} report",
            params=params,
        )
        return _decimal_safe(payload)

    def production_verification(
        self,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
        page_size: int = 100,
        max_pages_per_resource: int = 1000,
    ) -> dict[str, Any]:
        verification = self.verify_company_identity()
        record_counts: dict[str, int] = {"company": 1}
        report_availability: dict[str, bool] = {}
        failures: list[dict[str, str]] = []

        for resource in RESOURCE_ENTITY:
            try:
                records = self.list_all_resource(
                    resource,
                    limit=page_size,
                    max_pages=max_pages_per_resource,
                )
                record_counts[resource] = len(records)
            except QuickBooksConnectorError as exc:
                record_counts[resource] = 0
                failures.append({"operation": f"resource:{resource}", "message": str(exc)})

        for report_key in REPORT_NAMES:
            try:
                self.report(report_key, start_date=start_date, end_date=end_date)
                report_availability[report_key] = True
            except QuickBooksConnectorError as exc:
                report_availability[report_key] = False
                failures.append({"operation": f"report:{report_key}", "message": str(exc)})

        status = "healthy" if not failures else "degraded"
        if failures:
            self._store().record_sync_failure("QuickBooks verification completed with read errors", status="degraded")
        return {
            "connector": self.name,
            "organization_id": self._store().organization_id,
            "status": status,
            **verification,
            "authorization_status": "authorized",
            "refresh_verification_status": self._store().metadata().get("last_refresh_status"),
            "connected_realm_status": "present",
            "record_counts": record_counts,
            "report_availability": report_availability,
            "checkpoint_status": "available" if self._store().metadata().get("last_successful_sync_at") else "not_started",
            "last_successful_sync_time": self._store().metadata().get("last_successful_sync_at"),
            "last_safe_error_summary": self._store().metadata().get("last_error_summary"),
            "reauthorization_required": bool(self._store().metadata().get("reauthorization_required")),
            "failures": failures,
            "secrets_exposed": False,
        }

    def safe_status(self, *, include_resources: bool = False) -> dict[str, Any]:
        metadata = self._store_or_none().metadata() if self._store_or_none() else {}
        details: dict[str, Any] = {
            "organization_id": self._store_or_none().organization_id if self._store_or_none() else None,
            "expected_company_name": expected_company_name(),
            "verified_company_name": metadata.get("verified_company_name"),
            "identity_verification_status": metadata.get("verification_status", "authorization_required"),
            "authorization_status": "authorized" if metadata.get("authorized") else "authorization_required",
            "refresh_verification_status": metadata.get("last_refresh_status"),
            "last_successful_sync_time": metadata.get("last_successful_sync_at"),
            "last_safe_error_summary": metadata.get("last_error_summary"),
            "reauthorization_required": bool(metadata.get("reauthorization_required", False)),
            "connected_realm_status": "present" if metadata.get("authorized") else "absent",
            "read_only": True,
            "secrets_exposed": False,
        }
        if include_resources:
            details["resources"] = list(self.discover())
        return details

    @contextmanager
    def organization_sync_lock(self):
        organization_id = self._store().organization_id
        with _ORG_LOCKS_GUARD:
            lock = _ORG_LOCKS.setdefault(organization_id, threading.Lock())
        acquired = lock.acquire(blocking=False)
        if not acquired:
            raise QuickBooksConnectorError(
                "QuickBooks synchronization is already running for this organization",
                status=ConnectorStatus.DEGRADED,
            )
        try:
            yield
        finally:
            lock.release()

    def _store(self) -> QuickBooksCredentialStore:
        if self._credential_store is None:
            raise QuickBooksConnectorError("QuickBooks organization context is required", status=ConnectorStatus.AUTHORIZATION_REQUIRED)
        return self._credential_store

    def _store_or_none(self) -> QuickBooksCredentialStore | None:
        return self._credential_store

    def _require_realm_id(self) -> str:
        self.authenticate()
        if not self._realm_id:
            raise QuickBooksConnectorError("QuickBooks realm ID is unavailable", status=ConnectorStatus.AUTHORIZATION_REQUIRED)
        return self._realm_id

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=self._timeout_seconds())
        return self._client

    def _refresh_access_token(self) -> None:
        try:
            credential = self._store().load_credential()
        except QuickBooksCredentialError as exc:
            raise QuickBooksConnectorError(str(exc), status=ConnectorStatus.AUTHORIZATION_REQUIRED) from exc
        self._realm_id = credential.realm_id
        client_id = os.environ["POLARIS_QBO_CLIENT_ID"]
        client_secret = os.environ["POLARIS_QBO_CLIENT_SECRET"]
        basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        try:
            response = self._http().post(
                self._token_url(),
                data={"grant_type": "refresh_token", "refresh_token": credential.refresh_token},
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Basic {basic}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
        except httpx.TimeoutException as exc:
            message = "QuickBooks token refresh timed out"
            self._store().record_refresh_failure(message)
            raise QuickBooksConnectorError(message, status=ConnectorStatus.DEGRADED, retryable=True) from exc
        except httpx.HTTPError as exc:
            message = "QuickBooks token refresh failed"
            self._store().record_refresh_failure(message)
            raise QuickBooksConnectorError(message, status=ConnectorStatus.DEGRADED, retryable=True) from exc

        payload = self._json_response(response, "OAuth token refresh")
        access_token = payload.get("access_token")
        rotated_refresh_token = payload.get("refresh_token")
        if not isinstance(access_token, str) or not access_token:
            message = "QuickBooks token refresh returned no access token"
            self._store().record_refresh_failure(message)
            raise QuickBooksConnectorError(message, status=ConnectorStatus.REAUTHORIZATION_REQUIRED)
        if isinstance(rotated_refresh_token, str) and rotated_refresh_token:
            try:
                self._store().rotate_refresh_token(
                    realm_id=credential.realm_id,
                    refresh_token=rotated_refresh_token,
                    scopes=str(payload.get("scope") or credential.scopes),
                )
            except QuickBooksCredentialError as exc:
                raise QuickBooksConnectorError(str(exc), status=ConnectorStatus.DEGRADED) from exc
        self._access_token = access_token
        self._access_token_expires_at = self._now() + int(payload.get("expires_in", 3600))

    def _get(self, resource: str, *, operation: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        realm_id = self._require_realm_id()
        query_params = {"minorversion": self._minor_version()}
        if params:
            query_params.update(params)
        path = f"/v3/company/{realm_id}/{resource}"
        return self._request_json("GET", path, operation=operation, params=query_params)

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        operation: str,
        params: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        last_error: QuickBooksConnectorError | None = None
        for attempt in range(1, self._max_attempts() + 1):
            self.authenticate()
            try:
                response = self._http().request(
                    method,
                    f"{self._api_base_url()}{path}",
                    params=params,
                    json=json_body,
                    headers={
                        "Accept": "application/json",
                        "Authorization": f"Bearer {self._access_token}",
                        "X-Polaris-Correlation": _correlation_id(),
                    },
                )
                if response.status_code == 401 and attempt < self._max_attempts():
                    self._access_token = None
                    self._refresh_access_token()
                    continue
                return self._json_response(response, operation)
            except QuickBooksConnectorError as exc:
                last_error = exc
                if not exc.retryable or attempt == self._max_attempts():
                    raise
                self._sleep(self._retry_delay(attempt))
            except httpx.TimeoutException as exc:
                last_error = QuickBooksConnectorError(
                    f"QuickBooks {operation} timed out",
                    status=ConnectorStatus.DEGRADED,
                    retryable=True,
                )
                if attempt == self._max_attempts():
                    raise last_error from exc
                self._sleep(self._retry_delay(attempt))
            except httpx.HTTPError as exc:
                last_error = QuickBooksConnectorError(
                    f"QuickBooks {operation} failed",
                    status=ConnectorStatus.DEGRADED,
                    retryable=True,
                )
                if attempt == self._max_attempts():
                    raise last_error from exc
                self._sleep(self._retry_delay(attempt))
        raise last_error or QuickBooksConnectorError(f"QuickBooks {operation} failed")

    def _json_response(self, response: httpx.Response, operation: str) -> dict[str, Any]:
        if response.status_code == 429:
            raise QuickBooksConnectorError(
                f"QuickBooks {operation} is rate limited",
                status=ConnectorStatus.RATE_LIMITED,
                retryable=True,
            )
        if response.status_code in _REAUTH_CODES:
            message = f"QuickBooks {operation} authorization failed with HTTP {response.status_code}"
            self._store().record_refresh_failure(message, reauthorization_required=response.status_code in {400, 401})
            raise QuickBooksConnectorError(message, status=ConnectorStatus.REAUTHORIZATION_REQUIRED)
        if response.status_code >= 500:
            raise QuickBooksConnectorError(
                f"QuickBooks {operation} failed with HTTP {response.status_code}",
                status=ConnectorStatus.DEGRADED,
                retryable=True,
            )
        if response.status_code >= 400:
            raise QuickBooksConnectorError(
                f"QuickBooks {operation} failed with HTTP {response.status_code}",
                status=ConnectorStatus.DEGRADED,
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise QuickBooksConnectorError(f"QuickBooks {operation} returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise QuickBooksConnectorError(f"QuickBooks {operation} returned an unexpected response")
        return payload

    def _revoke_token(self, token: str) -> None:
        client_id = os.environ["POLARIS_QBO_CLIENT_ID"]
        client_secret = os.environ["POLARIS_QBO_CLIENT_SECRET"]
        basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        response = self._http().post(
            self._revoke_url(),
            json={"token": token},
            headers={
                "Accept": "application/json",
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/json",
            },
        )
        if response.status_code >= 400:
            raise QuickBooksConnectorError(
                f"QuickBooks token revocation failed with HTTP {response.status_code}",
                status=ConnectorStatus.DEGRADED,
            )

    @staticmethod
    def _mode() -> str:
        return os.getenv("POLARIS_QBO_ENVIRONMENT", "production").strip().lower()

    def _api_base_url(self) -> str:
        configured = os.getenv("POLARIS_QBO_API_BASE_URL")
        if configured:
            return configured.rstrip("/")
        return SANDBOX_API_BASE_URL if self._mode() == "sandbox" else API_BASE_URL

    @staticmethod
    def _token_url() -> str:
        return os.getenv("POLARIS_QBO_TOKEN_URL", TOKEN_URL)

    @staticmethod
    def _revoke_url() -> str:
        return os.getenv("POLARIS_QBO_REVOKE_URL", REVOKE_URL)

    @staticmethod
    def _minor_version() -> str:
        return os.getenv("POLARIS_QBO_MINOR_VERSION", MINOR_VERSION)

    @staticmethod
    def _timeout_seconds() -> float:
        return float(os.getenv("POLARIS_QBO_REQUEST_TIMEOUT_SECONDS", "20"))

    @staticmethod
    def _max_attempts() -> int:
        return max(1, int(os.getenv("POLARIS_QBO_MAX_ATTEMPTS", "3")))

    @staticmethod
    def _retry_delay(attempt: int) -> float:
        base = float(os.getenv("POLARIS_QBO_RETRY_BASE_SECONDS", "0.25"))
        return base * (2 ** (attempt - 1))


def expected_company_name() -> str:
    return os.getenv("POLARIS_QBO_EXPECTED_COMPANY_NAME", EXPECTED_COMPANY_NAME).strip() or EXPECTED_COMPANY_NAME


def _normalize_company_name(value: str) -> str:
    return " ".join(value.strip().casefold().split())


def _parse_cursor(cursor: int | str | None) -> int:
    if cursor is None:
        return 1
    try:
        parsed = int(cursor)
    except (TypeError, ValueError) as exc:
        raise QuickBooksConnectorError("QuickBooks cursor is invalid") from exc
    if parsed < 1:
        raise QuickBooksConnectorError("QuickBooks cursor is invalid")
    return parsed


def _escape_query_literal(value: str) -> str:
    return value.replace("'", "\\'")


def _correlation_id() -> str:
    return f"qbo-{int(time.time() * 1000)}"


def _redact(value: str) -> str:
    redacted = value
    for marker in ("access_token", "refresh_token", "client_secret", "authorization", "realmId", "code", "state"):
        redacted = redacted.replace(marker + "=", marker + "=[REDACTED]")
    if "Bearer " in redacted:
        redacted = redacted.split("Bearer ", 1)[0] + "Bearer [REDACTED]"
    return redacted


def _decimal_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _decimal_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_decimal_safe(item) for item in value]
    if isinstance(value, float):
        return str(Decimal(str(value)))
    return value


def decimal_string(value: Any) -> str | None:
    if value is None or value == "":
        return None
    try:
        return str(Decimal(str(value)))
    except (InvalidOperation, ValueError):
        return None
