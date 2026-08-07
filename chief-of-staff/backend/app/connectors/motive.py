"""Motive Company API Key connector shell for read-only verification and vehicle ingestion."""

from __future__ import annotations

import logging
import os
import random
import time
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from app.connectors.base import BaseConnector
from app.connectors.models import ConnectorHealth, ConnectorStatus, SyncResult
from app.connectors.motive_contracts import MotiveVehicle

logger = logging.getLogger(__name__)

MOTIVE_API_BASE_URL = "https://api.gomotive.com"
MOTIVE_VERIFICATION_ENDPOINT = "/v1/vehicles"
MOTIVE_VERIFICATION_PARAMS = {"per_page": 1, "page_no": 1}
MOTIVE_VEHICLES_ENDPOINT = "/v1/vehicles"
MOTIVE_VEHICLES_PER_PAGE = 100
MOTIVE_AUTHENTICATION_METHOD = "company_api_key"
MOTIVE_CREDENTIAL_SOURCE = "render_environment"
MOTIVE_CONFIRMED_ENDPOINTS = (
    "/v1/vehicles",
    "/v1/users",
    "/v1/vehicle_utilization",
    "/v1/driver_utilization",
    "/v1/ifta/summary",
)
MOTIVE_RESOURCES = (
    "connection_verification",
    "vehicles",
    "users_driver_identity_filtering_deferred",
    "vehicle_utilization",
    "driver_utilization",
    "ifta_summary",
)
_REAUTH_CODES = {401, 403}
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class MotiveConnectorError(RuntimeError):
    """Safe connector error that never includes Motive credentials or raw provider payloads."""

    def __init__(
        self,
        message: str,
        *,
        status: ConnectorStatus = ConnectorStatus.DEGRADED,
        retryable: bool = False,
        code: str | None = None,
        http_status: int | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(_sanitize(message))
        self.status = status
        self.retryable = retryable
        self.code = code or status.value
        self.http_status = http_status
        self.retry_after = retry_after


class MotiveConnector(BaseConnector):
    """Expose safe Motive status, verification, and vehicle-only read ingestion."""

    def __init__(
        self,
        *,
        organization_id: str | None = None,
        http_client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        jitter: Callable[[], float] = random.random,
        max_vehicle_pages: int | None = None,
    ) -> None:
        super().__init__(name="motive")
        self.organization_id = organization_id
        self._client = http_client
        self._sleep = sleep
        self._jitter = jitter
        self._max_vehicle_pages = max_vehicle_pages

    def validate_configuration(self) -> None:
        if not _api_key_present():
            raise MotiveConnectorError("Motive Company API Key is not configured", status=ConnectorStatus.NOT_CONFIGURED, code="api_key_missing")

    def authenticate(self) -> None:
        self.validate_configuration()

    def health(self, *, persisted_status: dict[str, Any] | None = None) -> ConnectorHealth:
        details = self.safe_status(persisted_status=persisted_status)
        status_value = str(details.get("connection_status") or "not_configured")
        status = _connector_status(status_value)
        message = _status_message(status_value)
        return ConnectorHealth(
            name=self.name,
            status=status,
            checked_at=datetime.now(timezone.utc),
            last_sync_at=_parse_datetime(details.get("last_successful_sync_at")),
            message=message,
            details=details,
        )

    def discover(self) -> Sequence[str]:
        return MOTIVE_RESOURCES

    def sync(self) -> SyncResult:
        started_at = datetime.now(timezone.utc)
        return SyncResult(
            connector=self.name,
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
            records_read=0,
            records_written=0,
            events_published=0,
            success=False,
            errors=["Motive broad synchronization is deferred; use vehicle-only manual sync."],
        )

    def disconnect(self) -> None:
        raise MotiveConnectorError(
            "Motive Company API Key is managed by administrator environment configuration",
            status=ConnectorStatus.CONFIGURED_UNVERIFIED if _api_key_present() else ConnectorStatus.NOT_CONFIGURED,
            code="environment_managed",
        )

    def safe_status(self, *, persisted_status: dict[str, Any] | None = None) -> dict[str, Any]:
        configured = _api_key_present()
        connection_status = "configured_unverified" if configured else "not_configured"
        authorization_required = not configured
        if persisted_status and configured:
            connection_status = str(persisted_status.get("connection_status") or connection_status)
            authorization_required = bool(persisted_status.get("authorization_required", connection_status == "authorization_required"))
        return {
            "provider": "motive",
            "authentication_method": MOTIVE_AUTHENTICATION_METHOD,
            "credential_source": MOTIVE_CREDENTIAL_SOURCE,
            "credential_precedence": [MOTIVE_CREDENTIAL_SOURCE],
            "configured_by_administrator": configured,
            "key_present": configured,
            "token_present": False,
            "authorized": configured and not authorization_required,
            "connection_status": connection_status,
            "authorization_required": authorization_required,
            "last_verified_at": persisted_status.get("last_verified_at") if persisted_status else None,
            "last_successful_sync_at": persisted_status.get("last_successful_sync_at") if persisted_status else None,
            "last_error_code": persisted_status.get("last_error_code") if persisted_status else None,
            "last_error_message_sanitized": persisted_status.get("last_error_message_sanitized") if persisted_status else None,
            "records_read": persisted_status.get("records_read") if persisted_status else 0,
            "vehicle_sync_enabled": True,
            "last_vehicle_sync_at": persisted_status.get("last_vehicle_sync_at") if persisted_status else None,
            "last_vehicle_sync_status": persisted_status.get("last_vehicle_sync_status") if persisted_status else None,
            "vehicle_records_stored": persisted_status.get("vehicle_records_stored") if persisted_status else 0,
            "last_vehicle_records_read": persisted_status.get("last_vehicle_records_read") if persisted_status else 0,
            "last_vehicle_pages_read": persisted_status.get("last_vehicle_pages_read") if persisted_status else 0,
            "read_only": True,
            "production_sync_enabled": False,
            "broad_sync_enabled": False,
            "verification_endpoint": MOTIVE_VERIFICATION_ENDPOINT,
            "verification_params": dict(MOTIVE_VERIFICATION_PARAMS),
            "vehicle_sync_endpoint": MOTIVE_VEHICLES_ENDPOINT,
            "confirmed_endpoints": list(MOTIVE_CONFIRMED_ENDPOINTS),
            "driver_user_pagination": {"endpoint": "/v1/users", "per_page_max": 100, "page_no": "one_based", "total_field": "pagination.total"},
            "production_certified": False,
            "vehicle_ingestion_certified": bool((persisted_status or {}).get("last_vehicle_sync_status") == "success"),
            "deferred_resources": ["drivers", "driver_role_filtering", "vehicle_utilization", "driver_utilization", "ifta_summary", "broad_sync", "hos", "safety", "dvir", "fault_codes", "trips", "maintenance", "fuel_purchases", "webhooks", "fleet_kpis", "multi_tenant_oauth"],
            "secrets_exposed": False,
        }

    def verify_connection(self) -> dict[str, Any]:
        self.validate_configuration()
        payload = self._request_vehicle_probe()
        records_read = _records_read_from_vehicle_payload(payload)
        verified_at = datetime.now(timezone.utc)
        return {
            "connector": self.name,
            "status": "connected",
            "verified_at": verified_at.isoformat(),
            "endpoint": MOTIVE_VERIFICATION_ENDPOINT,
            "request": {"method": "GET", "path": MOTIVE_VERIFICATION_ENDPOINT, "params": dict(MOTIVE_VERIFICATION_PARAMS), "authentication": "X-API-Key"},
            "records_read": records_read,
            "records_written": 0,
            "production_certified": False,
            "secrets_exposed": False,
        }

    def list_vehicles(self, *, organization_id: str, organization_slug: str) -> dict[str, Any]:
        """Read all Motive vehicles using the confirmed one-based page_no contract."""
        self.validate_configuration()
        vehicles: list[MotiveVehicle] = []
        pages_read = 0
        retrieved = 0
        total: int | None = None
        seen_pages: set[int] = set()
        for page_no in range(1, self._vehicle_page_limit() + 1):
            if page_no in seen_pages:
                raise MotiveConnectorError("Motive vehicle pagination repeated a page", status=ConnectorStatus.FAILED, code="provider_contract_error")
            seen_pages.add(page_no)
            params = {"per_page": MOTIVE_VEHICLES_PER_PAGE, "page_no": page_no}
            payload = self._request_json(MOTIVE_VEHICLES_ENDPOINT, params=params, operation="vehicle_sync")
            page_items = _vehicle_items(payload)
            pages_read += 1
            if total is None:
                total = _pagination_total(payload)
            if not page_items:
                break
            for item in page_items:
                vehicles.append(_normalize_vehicle(item, organization_id=organization_id, organization_slug=organization_slug))
            retrieved += len(page_items)
            if total is not None and retrieved >= total:
                break
        else:
            raise MotiveConnectorError("Motive vehicle pagination exceeded the maximum page guard", status=ConnectorStatus.FAILED, code="provider_contract_error")
        return {"vehicles": vehicles, "pages_read": pages_read, "records_read": len(vehicles), "pagination_total": total}

    def _request_vehicle_probe(self) -> dict[str, Any]:
        return self._request_json(MOTIVE_VERIFICATION_ENDPOINT, params=MOTIVE_VERIFICATION_PARAMS, operation="verification")

    def _request_json(self, endpoint: str, *, params: dict[str, int], operation: str) -> dict[str, Any]:
        last_error: MotiveConnectorError | None = None
        for attempt in range(1, _max_attempts() + 1):
            try:
                logger.info(
                    "MOTIVE API KEY REQUEST",
                    extra={
                        "motive_operation": operation,
                        "organization_id": self.organization_id,
                        "endpoint_path": endpoint,
                        "attempt": attempt,
                    },
                )
                response = self._http().get(
                    f"{self._base_url()}{endpoint}",
                    params=params,
                    headers={"Accept": "application/json", "X-API-Key": _api_key()},
                )
                payload = self._json_response(response)
                logger.info(
                    "MOTIVE API KEY VERIFY SUCCESS" if operation == "verification" else "MOTIVE API KEY VEHICLES PAGE SUCCESS",
                    extra={
                        "motive_operation": operation,
                        "organization_id": self.organization_id,
                        "endpoint_path": endpoint,
                        "http_status": response.status_code,
                        "records_read": _records_read_from_vehicle_payload(payload),
                        "rate_limited": False,
                        "page_no": params.get("page_no"),
                    },
                )
                return payload
            except MotiveConnectorError as exc:
                last_error = exc
                logger.info(
                    "MOTIVE API KEY REQUEST ERROR",
                    extra={
                        "motive_operation": operation,
                        "organization_id": self.organization_id,
                        "endpoint_path": endpoint,
                        "http_status": exc.http_status,
                        "error_code": exc.code,
                        "rate_limited": exc.status == ConnectorStatus.RATE_LIMITED,
                        "retry_after": exc.retry_after,
                        "attempt": attempt,
                        "page_no": params.get("page_no"),
                    },
                )
                if not exc.retryable or attempt == _max_attempts():
                    raise
                self._sleep(_retry_delay(attempt, exc.retry_after, self._jitter()))
            except httpx.TimeoutException as exc:
                last_error = MotiveConnectorError("Motive request timed out", status=ConnectorStatus.FAILED, retryable=True, code="provider_timeout")
                if attempt == _max_attempts():
                    raise last_error from exc
                self._sleep(_retry_delay(attempt, None, self._jitter()))
            except httpx.HTTPError as exc:
                last_error = MotiveConnectorError("Motive request failed due to a network error", status=ConnectorStatus.FAILED, retryable=True, code="network_failure")
                if attempt == _max_attempts():
                    raise last_error from exc
                self._sleep(_retry_delay(attempt, None, self._jitter()))
        raise last_error or MotiveConnectorError("Motive request failed", status=ConnectorStatus.FAILED, code="provider_unavailable")

    def _json_response(self, response: httpx.Response) -> dict[str, Any]:
        retry_after = _retry_after_seconds(response.headers.get("Retry-After"))
        if response.status_code == 429:
            raise MotiveConnectorError("Motive request was rate limited", status=ConnectorStatus.RATE_LIMITED, retryable=True, code="rate_limited", http_status=429, retry_after=retry_after)
        if response.status_code in _REAUTH_CODES:
            raise MotiveConnectorError(
                f"Motive API key authorization failed with HTTP {response.status_code}",
                status=ConnectorStatus.AUTHORIZATION_REQUIRED,
                retryable=False,
                code="permission_denied" if response.status_code == 403 else "authorization_required",
                http_status=response.status_code,
            )
        if response.status_code in _RETRYABLE_STATUS_CODES:
            raise MotiveConnectorError(
                f"Motive provider returned HTTP {response.status_code}",
                status=ConnectorStatus.FAILED,
                retryable=True,
                code="provider_unavailable",
                http_status=response.status_code,
                retry_after=retry_after,
            )
        if response.status_code >= 400:
            raise MotiveConnectorError(
                f"Motive request failed with HTTP {response.status_code}",
                status=ConnectorStatus.FAILED,
                retryable=False,
                code=f"http_{response.status_code}",
                http_status=response.status_code,
            )
        if not response.content:
            raise MotiveConnectorError("Motive returned an empty response", status=ConnectorStatus.FAILED, code="provider_contract_error", http_status=response.status_code)
        try:
            decoded = response.json()
        except ValueError as exc:
            raise MotiveConnectorError("Motive returned invalid JSON", status=ConnectorStatus.FAILED, code="provider_contract_error", http_status=response.status_code) from exc
        if not isinstance(decoded, dict):
            raise MotiveConnectorError("Motive returned an unexpected response shape", status=ConnectorStatus.FAILED, code="provider_contract_error", http_status=response.status_code)
        return decoded

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=_timeout_seconds())
        return self._client

    @staticmethod
    def _base_url() -> str:
        return os.getenv("POLARIS_MOTIVE_API_BASE_URL", MOTIVE_API_BASE_URL).rstrip("/")

    def _vehicle_page_limit(self) -> int:
        configured = int(os.getenv("POLARIS_MOTIVE_VEHICLE_MAX_PAGES", "100"))
        if self._max_vehicle_pages is not None:
            configured = self._max_vehicle_pages
        return min(max(configured, 1), 1000)


def _connector_status(value: str) -> ConnectorStatus:
    mapping = {
        "not_configured": ConnectorStatus.NOT_CONFIGURED,
        "configured_unverified": ConnectorStatus.CONFIGURED_UNVERIFIED,
        "connected": ConnectorStatus.CONNECTED,
        "authorization_required": ConnectorStatus.AUTHORIZATION_REQUIRED,
        "running": ConnectorStatus.RUNNING,
        "success": ConnectorStatus.SUCCESS,
        "failed": ConnectorStatus.FAILED,
        "rate_limited": ConnectorStatus.RATE_LIMITED,
    }
    return mapping.get(value, ConnectorStatus.DEGRADED)


def _status_message(value: str) -> str:
    if value == "not_configured":
        return "Motive Company API Key is not configured."
    if value == "configured_unverified":
        return "Motive Company API Key is configured by administrator and awaiting verification."
    if value == "connected":
        return "Motive Company API Key passed limited read-only vehicle verification."
    if value == "rate_limited":
        return "Motive verification is rate limited; Retry-After is honored when present."
    if value == "authorization_required":
        return "Motive Company API Key authorization is required."
    return "Motive connector status is available."


def _vehicle_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    value = payload.get("vehicles")
    if value is None:
        value = payload.get("data")
    if not isinstance(value, list):
        raise MotiveConnectorError("Motive vehicle response did not include a vehicle list", status=ConnectorStatus.FAILED, code="provider_contract_error")
    items: list[dict[str, Any]] = []
    for raw in value:
        if isinstance(raw, dict) and isinstance(raw.get("vehicle"), dict):
            raw = raw["vehicle"]
        if not isinstance(raw, dict):
            raise MotiveConnectorError("Motive vehicle response included an unexpected vehicle item", status=ConnectorStatus.FAILED, code="provider_contract_error")
        items.append(raw)
    return items


def _pagination_total(payload: dict[str, Any]) -> int | None:
    pagination = payload.get("pagination")
    if not isinstance(pagination, dict) or pagination.get("total") is None:
        return None
    try:
        total = int(pagination["total"])
    except (TypeError, ValueError) as exc:
        raise MotiveConnectorError("Motive pagination total was not numeric", status=ConnectorStatus.FAILED, code="provider_contract_error") from exc
    return max(total, 0)


def _normalize_vehicle(raw: dict[str, Any], *, organization_id: str, organization_slug: str) -> MotiveVehicle:
    provider_vehicle_id = _string(raw.get("id") or raw.get("provider_vehicle_id"))
    if not provider_vehicle_id:
        raise MotiveConnectorError("Motive vehicle did not include a provider vehicle id", status=ConnectorStatus.FAILED, code="provider_contract_error")
    observed_at = _parse_datetime(raw.get("updated_at") or raw.get("last_updated_at") or raw.get("created_at"))
    metadata = {"source_keys": sorted(str(key) for key in raw.keys() if _safe_metadata_key(str(key)))}
    return MotiveVehicle(
        organization_id=organization_id,
        organization_slug=organization_slug,
        provider_vehicle_id=provider_vehicle_id,
        source_endpoint=MOTIVE_VEHICLES_ENDPOINT,
        unit_number=_string(raw.get("number") or raw.get("unit_number") or raw.get("name")),
        vin=_string(raw.get("vin")),
        make=_string(raw.get("make")),
        model=_string(raw.get("model")),
        year=_int_or_none(raw.get("year")),
        license_plate=_string(raw.get("license_plate") or raw.get("license_plate_number")),
        status=_string(raw.get("status")),
        observed_at=observed_at,
        metadata=metadata,
    )


def _records_read_from_vehicle_payload(payload: dict[str, Any]) -> int:
    try:
        return len(_vehicle_items(payload))
    except MotiveConnectorError:
        if isinstance(payload.get("vehicle"), dict):
            return 1
        return 0


def _api_key_present() -> bool:
    return bool(os.getenv("MOTIVE_API_KEY"))


def _api_key() -> str:
    key = os.getenv("MOTIVE_API_KEY")
    if not key:
        raise MotiveConnectorError("Motive Company API Key is not configured", status=ConnectorStatus.NOT_CONFIGURED, code="api_key_missing")
    return key


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed


def _string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_metadata_key(key: str) -> bool:
    lowered = key.lower()
    return not any(marker in lowered for marker in ("token", "secret", "authorization", "api_key", "x-api-key"))


def _timeout_seconds() -> float:
    return float(os.getenv("POLARIS_MOTIVE_REQUEST_TIMEOUT_SECONDS", "10"))


def _max_attempts() -> int:
    return min(max(int(os.getenv("POLARIS_MOTIVE_MAX_ATTEMPTS", "2")), 1), 3)


def _retry_delay(attempt: int, retry_after: float | None, jitter: float) -> float:
    if retry_after is not None:
        return max(retry_after, 0.0)
    base = float(os.getenv("POLARIS_MOTIVE_RETRY_BASE_SECONDS", "0.25"))
    return min(base * (2 ** (attempt - 1)) + min(max(jitter, 0.0), 1.0) * base, 5.0)


def _retry_after_seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(float(value), 0.0)
    except ValueError:
        try:
            return max((parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds(), 0.0)
        except (TypeError, ValueError):
            return None


def _sanitize(message: str) -> str:
    sanitized = " ".join(str(message).split())
    for marker in ("x-api-key", "motive_api_key", "api_key", "access_token", "refresh_token", "authorization", "bearer", "client_secret", "code", "token", "secret"):
        sanitized = sanitized.replace(marker, "credential")
        sanitized = sanitized.replace(marker.upper(), "CREDENTIAL")
    return sanitized[:500]
