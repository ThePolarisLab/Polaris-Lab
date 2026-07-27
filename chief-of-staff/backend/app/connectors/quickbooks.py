"""Read-only QuickBooks Online production connector for the Chief of Staff API."""

from __future__ import annotations

import base64
import json
import os
import time
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.connectors.base import BaseConnector
from app.connectors.models import ConnectorHealth, ConnectorStatus, SyncResult


EXPECTED_COMPANY_NAME = "MOR LOGISTICS MANITOBA LIMITED"
TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
API_BASE_URL = "https://quickbooks.api.intuit.com"


class QuickBooksConnectorError(RuntimeError):
    """Safe connector error that never contains OAuth credential values."""


class QuickBooksConnector(BaseConnector):
    """Verify and synchronize a read-only QuickBooks Online company connection.

    Credentials are read lazily from process environment variables so importing
    the application never requires or exposes secrets.
    """

    def __init__(
        self,
        *,
        opener: Callable[..., Any] = urlopen,
        now: Callable[[], float] = time.time,
    ) -> None:
        super().__init__(name="quickbooks")
        self._opener = opener
        self._now = now
        self._access_token: str | None = None
        self._access_token_expires_at = 0.0
        self._last_sync_at: datetime | None = None
        self._company_name: str | None = None

    def validate_configuration(self) -> None:
        missing = [
            name
            for name in (
                "POLARIS_QBO_CLIENT_ID",
                "POLARIS_QBO_CLIENT_SECRET",
                "POLARIS_QBO_REFRESH_TOKEN",
                "POLARIS_QBO_REALM_ID",
            )
            if not os.getenv(name)
        ]
        if missing:
            raise QuickBooksConnectorError(
                "QuickBooks is not configured. Missing environment variables: "
                + ", ".join(missing)
            )

    def authenticate(self) -> None:
        self.validate_configuration()
        if self._access_token and self._now() < self._access_token_expires_at - 60:
            return

        client_id = os.environ["POLARIS_QBO_CLIENT_ID"]
        client_secret = os.environ["POLARIS_QBO_CLIENT_SECRET"]
        refresh_token = os.environ["POLARIS_QBO_REFRESH_TOKEN"]
        basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        request = Request(
            TOKEN_URL,
            data=urlencode(
                {"grant_type": "refresh_token", "refresh_token": refresh_token}
            ).encode(),
            headers={
                "Accept": "application/json",
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        payload = self._request_json(request, "OAuth token refresh")
        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise QuickBooksConnectorError("QuickBooks token refresh returned no access token")
        self._access_token = access_token
        self._access_token_expires_at = self._now() + int(payload.get("expires_in", 3600))

    def health(self) -> ConnectorHealth:
        started = datetime.now(timezone.utc)
        try:
            company = self._company_info()
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
            status = (
                ConnectorStatus.CONFIGURATION_ERROR
                if "not configured" in str(exc).lower()
                else ConnectorStatus.AUTHENTICATION_ERROR
            )
            return ConnectorHealth(name=self.name, status=status, message=str(exc))

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
            company = self._company_info()
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

    def _company_info(self) -> dict[str, Any]:
        self.authenticate()
        realm_id = os.environ["POLARIS_QBO_REALM_ID"]
        request = Request(
            f"{API_BASE_URL}/v3/company/{realm_id}/companyinfo/{realm_id}?minorversion=75",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self._access_token}",
            },
            method="GET",
        )
        payload = self._request_json(request, "company verification")
        company = payload.get("CompanyInfo")
        if not isinstance(company, dict):
            raise QuickBooksConnectorError("QuickBooks company information was not returned")
        return company

    def _request_json(self, request: Request, operation: str) -> dict[str, Any]:
        try:
            with self._opener(request, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise QuickBooksConnectorError(
                f"QuickBooks {operation} failed with HTTP {exc.code}"
            ) from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise QuickBooksConnectorError(f"QuickBooks {operation} failed") from exc
