"""Motive API-key connector shell for limited read-only verification."""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from typing import Any

import httpx

from app.connectors.base import BaseConnector
from app.connectors.models import ConnectorHealth, ConnectorStatus, SyncResult
from app.connectors.motive_credentials import MotiveCredentialError, MotiveCredentialStore

MOTIVE_API_BASE_URL = "https://api.gomotive.com"
MOTIVE_VERIFICATION_ENDPOINT = "/v1/vehicles"
MOTIVE_VERIFICATION_PARAMS = {"per_page": "1", "page_no": "1"}
MOTIVE_RESOURCES = (
    "connection_verification",
    "vehicles",
    "drivers_identity_contract_only",
    "vehicle_utilization",
    "driver_utilization",
    "ifta_summary",
)
_REAUTH_CODES = {401, 403}
logger = logging.getLogger(__name__)


class MotiveConnectorError(RuntimeError):
    """Safe connector error that never includes Motive credentials or raw provider payloads."""

    def __init__(self, message: str, *, status: ConnectorStatus = ConnectorStatus.DEGRADED, retryable: bool = False, code: str | None = None) -> None:
        super().__init__(_sanitize(message))
        self.status = status
        self.retryable = retryable
        self.code = code or status.value


class MotiveConnector(BaseConnector):
    """Expose safe Motive status and one narrow read-only verification call."""

    def __init__(
        self,
        *,
        http_client: httpx.Client | None = None,
        credential_store: MotiveCredentialStore | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        super().__init__(name="motive")
        self._client = http_client
        self._credential_store = credential_store
        self._sleep = sleep

    def validate_configuration(self) -> None:
        if not os.getenv("POLARIS_MOTIVE_TOKEN_ENCRYPTION_KEY") and not os.getenv("POLARIS_QBO_TOKEN_ENCRYPTION_KEY"):
            raise MotiveConnectorError(
                "Motive token encryption is not configured",
                status=ConnectorStatus.NOT_CONFIGURED,
                code="encryption_not_configured",
            )
        try:
            metadata = self._store().metadata(environment_mode=self._environment_mode())
        except MotiveCredentialError as exc:
            raise MotiveConnectorError(str(exc), status=ConnectorStatus.NOT_CONFIGURED) from exc
        if not metadata.get("key_present"):
            raise MotiveConnectorError("Motive API-key credential is not configured", status=ConnectorStatus.NOT_CONFIGURED)

    def authenticate(self) -> None:
        self.validate_configuration()
        self._store().load_api_key(environment_mode=self._environment_mode())

    def health(self) -> ConnectorHealth:
        details = self.safe_status()
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
            errors=["Motive broad synchronization is deferred; use verification only."],
        )

    def disconnect(self) -> None:
        self._store().delete(environment_mode=self._environment_mode())

    def safe_status(self) -> dict[str, Any]:
        store = self._store_or_none()
        metadata = store.metadata(environment_mode=self._environment_mode()) if store else {
            "provider": "motive",
            "authentication_method": "api_key",
            "connection_status": "not_configured",
            "key_present": False,
            "authorization_required": True,
            "secrets_exposed": False,
        }
        return {
            **metadata,
            "read_only": True,
            "production_sync_enabled": False,
            "verification_endpoint": MOTIVE_VERIFICATION_ENDPOINT,
            "verified_resources": ["vehicles", "vehicle_utilization", "driver_utilization", "ifta_summary"],
            "deferred_resources": ["driver_list", "hos", "safety", "dvir", "fault_codes", "trips", "maintenance", "fuel_purchases", "webhooks"],
            "secrets_exposed": False,
        }

    def verify_connection(self) -> dict[str, Any]:
        started = datetime.now(timezone.utc)
        environment_mode = self._environment_mode()
        try:
            credential = self._store().load_api_key(environment_mode=environment_mode)
            payload = self._request_verification_page(credential.api_key)
            records_read = _verification_record_count(payload)
            verified_at = datetime.now(timezone.utc)
            self._store().record_verification_success(environment_mode=environment_mode, verified_at=verified_at)
            return {
                "connector": self.name,
                "status": "connected",
                "verified_at": verified_at.isoformat(),
                "endpoint": MOTIVE_VERIFICATION_ENDPOINT,
                "request": {"method": "GET", "path": MOTIVE_VERIFICATION_ENDPOINT, "params": MOTIVE_VERIFICATION_PARAMS},
                "records_read": records_read,
                "records_written": 0,
                "production_certified": False,
                "secrets_exposed": False,
            }
        except MotiveConnectorError as exc:
            self._store_or_none() and self._store().record_verification_failure(
                environment_mode=environment_mode,
                status=exc.status.value,
                error_code=exc.code,
                error_message_sanitized=str(exc),
                authorization_required=exc.status in {ConnectorStatus.AUTHORIZATION_REQUIRED, ConnectorStatus.REAUTHORIZATION_REQUIRED},
            )
            raise
        finally:
            self._record_verification_history(started_at=started)

    def _request_verification_page(self, api_key: str) -> dict[str, Any]:
        last_error: MotiveConnectorError | None = None
        for attempt in range(1, self._max_attempts() + 1):
            try:
                response = self._http().get(
                    f"{self._base_url()}{MOTIVE_VERIFICATION_ENDPOINT}",
                    params=MOTIVE_VERIFICATION_PARAMS,
                    headers={"Accept": "application/json", "X-API-Key": api_key},
                )
                return self._json_response(response)
            except MotiveConnectorError as exc:
                last_error = exc
                if not exc.retryable or attempt == self._max_attempts():
                    raise
                self._sleep(self._retry_delay(attempt))
            except httpx.TimeoutException as exc:
                last_error = MotiveConnectorError("Motive verification timed out", status=ConnectorStatus.FAILED, retryable=True, code="timeout")
                if attempt == self._max_attempts():
                    raise last_error from exc
                self._sleep(self._retry_delay(attempt))
            except httpx.HTTPError as exc:
                last_error = MotiveConnectorError("Motive verification failed due to a network error", status=ConnectorStatus.FAILED, retryable=True, code="network_failure")
                if attempt == self._max_attempts():
                    raise last_error from exc
                self._sleep(self._retry_delay(attempt))
        raise last_error or MotiveConnectorError("Motive verification failed", status=ConnectorStatus.FAILED)

    def _json_response(self, response: httpx.Response) -> dict[str, Any]:
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            message = "Motive verification was rate limited"
            if retry_after:
                message += "; provider returned Retry-After"
            raise MotiveConnectorError(message, status=ConnectorStatus.RATE_LIMITED, retryable=False, code="rate_limited")
        if response.status_code in _REAUTH_CODES:
            raise MotiveConnectorError(
                f"Motive authorization failed with HTTP {response.status_code}",
                status=ConnectorStatus.AUTHORIZATION_REQUIRED,
                retryable=False,
                code=f"http_{response.status_code}",
            )
        if response.status_code >= 500:
            raise MotiveConnectorError(
                f"Motive provider returned HTTP {response.status_code}",
                status=ConnectorStatus.FAILED,
                retryable=True,
                code=f"http_{response.status_code}",
            )
        if response.status_code >= 400:
            raise MotiveConnectorError(
                f"Motive verification failed with HTTP {response.status_code}",
                status=ConnectorStatus.FAILED,
                retryable=False,
                code=f"http_{response.status_code}",
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise MotiveConnectorError("Motive verification returned invalid JSON", status=ConnectorStatus.FAILED, code="malformed_response") from exc
        if not isinstance(payload, dict):
            raise MotiveConnectorError("Motive verification returned an unexpected response", status=ConnectorStatus.FAILED, code="malformed_response")
        return payload

    def _record_verification_history(self, *, started_at: datetime) -> None:
        # Verification history persistence is handled by the API service layer once request context is available.
        return None

    def _store(self) -> MotiveCredentialStore:
        if self._credential_store is None:
            raise MotiveConnectorError("Motive organization context is required", status=ConnectorStatus.AUTHORIZATION_REQUIRED)
        return self._credential_store

    def _store_or_none(self) -> MotiveCredentialStore | None:
        return self._credential_store

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=self._timeout_seconds())
        return self._client

    @staticmethod
    def _base_url() -> str:
        return os.getenv("POLARIS_MOTIVE_API_BASE_URL", MOTIVE_API_BASE_URL).rstrip("/")

    @staticmethod
    def _environment_mode() -> str:
        return os.getenv("POLARIS_MOTIVE_ENVIRONMENT_MODE", "test").strip().lower() or "test"

    @staticmethod
    def _timeout_seconds() -> float:
        return float(os.getenv("POLARIS_MOTIVE_REQUEST_TIMEOUT_SECONDS", "10"))

    @staticmethod
    def _max_attempts() -> int:
        return min(max(int(os.getenv("POLARIS_MOTIVE_MAX_ATTEMPTS", "2")), 1), 2)

    @staticmethod
    def _retry_delay(attempt: int) -> float:
        return float(os.getenv("POLARIS_MOTIVE_RETRY_BASE_SECONDS", "0.25")) * attempt


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
        return "Motive API-key credential is not configured."
    if value == "configured_unverified":
        return "Motive API-key credential is configured but not verified."
    if value == "connected":
        return "Motive API-key credential passed limited read-only verification."
    if value == "rate_limited":
        return "Motive verification is rate limited; retry timing is not assumed."
    if value == "authorization_required":
        return "Motive authorization is required."
    return "Motive connector status is available."


def _verification_record_count(payload: dict[str, Any]) -> int:
    for key in ("vehicles", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return len(value)
    return 0


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _sanitize(message: str) -> str:
    sanitized = " ".join(str(message).split())
    for marker in ("x-api-key", "api_key", "apikey", "authorization", "token", "secret", "motive_api_key"):
        sanitized = sanitized.replace(marker, "credential")
        sanitized = sanitized.replace(marker.upper(), "CREDENTIAL")
    return sanitized[:500]
