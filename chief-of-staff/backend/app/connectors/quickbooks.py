"""Read-only QuickBooks Online production connector for the Chief of Staff API."""

from __future__ import annotations

import base64
import json
import os
import time
from collections.abc import Callable, Sequence
from datetime import date, datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from app.connectors.base import BaseConnector
from app.connectors.models import ConnectorHealth, ConnectorStatus, SyncResult
from app.connectors.quickbooks_credentials import (
    QuickBooksCredentialError,
    QuickBooksCredentialStore,
)

EXPECTED_COMPANY_NAME = "MOR LOGISTICS MANITOBA LIMITED"
TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
API_BASE_URL = "https://quickbooks.api.intuit.com"
MINOR_VERSION = "75"


class QuickBooksConnectorError(RuntimeError):
    """Safe connector error that never contains OAuth credential values."""


class QuickBooksConnector(BaseConnector):
    """Verify and synchronize a read-only QuickBooks Online company connection."""

    def __init__(
        self,
        *,
        opener: Callable[..., Any] = urlopen,
        now: Callable[[], float] = time.time,
        credential_store: QuickBooksCredentialStore | None = None,
    ) -> None:
        super().__init__(name="quickbooks")
        self._opener = opener
        self._now = now
        self._credential_store = credential_store
        self._access_token: str | None = None
        self._access_token_expires_at = 0.0
        self._realm_id: str | None = None
        self._last_sync_at: datetime | None = None
        self._company_name: str | None = None

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
                + ", ".join(missing)
            )
        try:
            self._realm_id, _ = self._store().load()
        except QuickBooksCredentialError as exc:
            raise QuickBooksConnectorError(str(exc)) from exc

    def authenticate(self) -> None:
        self.validate_configuration()
        if self._access_token and self._now() < self._access_token_expires_at - 60:
            return

        try:
            realm_id, refresh_token = self._store().load()
        except QuickBooksCredentialError as exc:
            raise QuickBooksConnectorError(str(exc)) from exc
        self._realm_id = realm_id
        client_id = os.environ["POLARIS_QBO_CLIENT_ID"]
        client_secret = os.environ["POLARIS_QBO_CLIENT_SECRET"]
        basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        request = Request(
            TOKEN_URL,
            data=urlencode({"grant_type": "refresh_token", "refresh_token": refresh_token}).encode(),
            headers={
                "Accept": "application/json",
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        payload = self._request_json(request, "OAuth token refresh")
        access_token = payload.get("access_token")
        rotated_refresh_token = payload.get("refresh_token")
        if not isinstance(access_token, str) or not access_token:
            raise QuickBooksConnectorError("QuickBooks token refresh returned no access token")
        if isinstance(rotated_refresh_token, str) and rotated_refresh_token:
            try:
                self._store().save(
                    realm_id=realm_id,
                    refresh_token=rotated_refresh_token,
                    scopes=str(payload.get("scope") or "com.intuit.quickbooks.accounting"),
                )
            except QuickBooksCredentialError as exc:
                raise QuickBooksConnectorError(str(exc)) from exc
        self._access_token = access_token
        self._access_token_expires_at = self._now() + int(payload.get("expires_in", 3600))

    def health(self) -> ConnectorHealth:
        started = datetime.now(timezone.utc)
        try:
            company = self.company_info()
            company_name = str(company.get("CompanyName") or "")
            if company_name != EXPECTED_COMPANY_NAME:
                return ConnectorHealth(
                    name=self.name,
                    status=ConnectorStatus.AUTHENTICATION_ERROR,
                    message="QuickBooks company identity does not match the configured organization.",
                    details={"expected_company": EXPECTED_COMPANY_NAME},
                )
            self._company_name = company_name
        except QuickBooksConnectorError as exc:
            message = str(exc)
            status_value = (
                ConnectorStatus.CONFIGURATION_ERROR
                if "not configured" in message.lower()
                or "not been authorized" in message.lower()
                or "organization context" in message.lower()
                else ConnectorStatus.AUTHENTICATION_ERROR
            )
            return ConnectorHealth(name=self.name, status=status_value, message=message)

        latency_ms = (datetime.now(timezone.utc) - started).total_seconds() * 1000
        return ConnectorHealth(
            name=self.name,
            status=ConnectorStatus.HEALTHY,
            checked_at=datetime.now(timezone.utc),
            latency_ms=round(latency_ms, 2),
            last_sync_at=self._last_sync_at,
            message=f"Connected to {self._company_name}.",
            details={
                "company_name": self._company_name,
                "read_only": True,
                "secrets_exposed": False,
                "resources": list(self.discover()),
            },
        )

    def discover(self) -> Sequence[str]:
        return (
            "company",
            "accounts",
            "customers",
            "vendors",
            "invoices",
            "payments",
            "bills",
            "purchases",
            "journal_entries",
            "profit_and_loss",
            "balance_sheet",
            "cash_flow",
            "aged_receivables",
            "aged_payables",
        )

    def sync(self) -> SyncResult:
        started_at = datetime.now(timezone.utc)
        records_read = 0
        errors: list[str] = []
        try:
            company = self.company_info()
            company_name = str(company.get("CompanyName") or "")
            if company_name != EXPECTED_COMPANY_NAME:
                raise QuickBooksConnectorError(
                    "QuickBooks company identity does not match the configured organization."
                )
            self._company_name = company_name
            records_read = 1
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

    def disconnect(self) -> None:
        self._access_token = None
        self._access_token_expires_at = 0.0
        self._realm_id = None

    def company_info(self) -> dict[str, Any]:
        """Return the connected company's QuickBooks metadata."""
        payload = self._get(
            f"companyinfo/{self._require_realm_id()}",
            operation="company information",
        )
        company = payload.get("CompanyInfo")
        if not isinstance(company, dict):
            raise QuickBooksConnectorError("QuickBooks company information was not returned")
        return company

    def accounts(self) -> list[dict[str, Any]]:
        """Return the active Chart of Accounts in stable display-name order."""
        query = "select * from Account where Active = true order by FullyQualifiedName"
        payload = self._get("query", operation="accounts query", params={"query": query})
        query_response = payload.get("QueryResponse")
        if not isinstance(query_response, dict):
            raise QuickBooksConnectorError("QuickBooks accounts response was malformed")
        accounts = query_response.get("Account", [])
        if not isinstance(accounts, list):
            raise QuickBooksConnectorError("QuickBooks accounts were not returned as a list")
        return [account for account in accounts if isinstance(account, dict)]

    def report(
        self,
        report_name: str,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
        accounting_method: str = "Accrual",
    ) -> dict[str, Any]:
        """Return one supported read-only financial report from QuickBooks."""
        supported = {"ProfitAndLoss", "BalanceSheet", "CashFlow"}
        if report_name not in supported:
            raise QuickBooksConnectorError(f"Unsupported QuickBooks report: {report_name}")
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
        return self._get(
            f"reports/{quote(report_name, safe='')}",
            operation=f"{report_name} report",
            params=params,
        )

    def _store(self) -> QuickBooksCredentialStore:
        if self._credential_store is None:
            raise QuickBooksConnectorError("QuickBooks organization context is required")
        return self._credential_store

    def _require_realm_id(self) -> str:
        self.authenticate()
        if not self._realm_id:
            raise QuickBooksConnectorError("QuickBooks realm ID is unavailable")
        return self._realm_id

    def _get(self, resource: str, *, operation: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        realm_id = self._require_realm_id()
        query_params = {"minorversion": MINOR_VERSION}
        if params:
            query_params.update(params)
        request = Request(
            f"{API_BASE_URL}/v3/company/{realm_id}/{resource}?{urlencode(query_params)}",
            headers={"Accept": "application/json", "Authorization": f"Bearer {self._access_token}"},
            method="GET",
        )
        return self._request_json(request, operation)

    def _request_json(self, request: Request, operation: str) -> dict[str, Any]:
        try:
            with self._opener(request, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
                if not isinstance(payload, dict):
                    raise QuickBooksConnectorError(
                        f"QuickBooks {operation} returned an unexpected response"
                    )
                return payload
        except HTTPError as exc:
            raise QuickBooksConnectorError(
                f"QuickBooks {operation} failed with HTTP {exc.code}"
            ) from exc
        except QuickBooksConnectorError:
            raise
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise QuickBooksConnectorError(f"QuickBooks {operation} failed") from exc
