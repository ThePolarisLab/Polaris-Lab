"""Motive OAuth connector shell for limited read-only verification."""

from __future__ import annotations

import os
import secrets
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import httpx

from app.connectors.base import BaseConnector
from app.connectors.models import ConnectorHealth, ConnectorStatus, SyncResult
from app.connectors.motive_credentials import MotiveCredentialError, MotiveCredentialStore
from app.database.database import SessionLocal
from app.models.motive import MotiveOAuthState
from app.organizations.models import Organization

MOTIVE_AUTHORIZATION_URL = "https://gomotive.com/oauth/authorize"
MOTIVE_TOKEN_URL = "https://gomotive.com/oauth/token"
MOTIVE_API_BASE_URL = "https://api.gomotive.com"
MOTIVE_VERIFICATION_ENDPOINT = "/v1/companies"
MOTIVE_OAUTH_SCOPES = (
    "companies.read",
    "users.read",
    "vehicles.read",
    "utilization.vehicle_utilization",
    "utilization.driver_utilization",
    "ifta_reports.summary",
)
MOTIVE_RESOURCES = (
    "connection_verification",
    "vehicles",
    "drivers_identity_contract_only",
    "vehicle_utilization",
    "driver_utilization",
    "ifta_summary",
)
_REAUTH_CODES = {401, 403}
_AUTHORIZATION_CODE_TTL_MINUTES = 10
_TOKEN_REFRESH_SKEW_SECONDS = 300


@dataclass(frozen=True, slots=True)
class _OAuthStateMetadata:
    organization_id: str
    organization_slug: str
    redirect_uri: str
    scopes: str


class MotiveConnectorError(RuntimeError):
    """Safe connector error that never includes Motive credentials or raw provider payloads."""

    def __init__(self, message: str, *, status: ConnectorStatus = ConnectorStatus.DEGRADED, retryable: bool = False, code: str | None = None) -> None:
        super().__init__(_sanitize(message))
        self.status = status
        self.retryable = retryable
        self.code = code or status.value


class MotiveOAuthService:
    """Organization-scoped Motive OAuth orchestration."""

    def __init__(
        self,
        *,
        http_client: httpx.Client | None = None,
        credential_store_factory: Callable[[str], MotiveCredentialStore] = MotiveCredentialStore,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = http_client
        self._credential_store_factory = credential_store_factory
        self._sleep = sleep

    def create_authorization_url(self, *, organization_id: str, identity_id: str, organization_slug: str) -> dict[str, Any]:
        self.validate_oauth_configuration()
        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(16)
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=_AUTHORIZATION_CODE_TTL_MINUTES)
        scopes = " ".join(MOTIVE_OAUTH_SCOPES)
        with SessionLocal.begin() as session:
            session.add(
                MotiveOAuthState(
                    state=state,
                    organization_id=organization_id,
                    identity_id=identity_id,
                    nonce=nonce,
                    redirect_uri=self.redirect_uri(),
                    scopes=scopes,
                    created_at=now,
                    expires_at=expires_at,
                )
            )
        params = {
            "client_id": self.client_id(),
            "redirect_uri": self.redirect_uri(),
            "response_type": "code",
            "scope": scopes,
            "state": state,
        }
        return {
            "authorization_url": f"{MOTIVE_AUTHORIZATION_URL}?{urlencode(params)}",
            "expires_at": expires_at.isoformat(),
            "organization_id": organization_id,
            "organization_slug": organization_slug,
            "requested_scopes": list(MOTIVE_OAUTH_SCOPES),
            "secrets_exposed": False,
        }

    def complete_authorization(self, *, state: str, code: str, expected_organization_id: str | None = None) -> dict[str, Any]:
        oauth_state = self._consume_state(state, expected_organization_id=expected_organization_id)
        token_payload = self._token_request(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": oauth_state.redirect_uri,
                "client_id": self.client_id(),
                "client_secret": self.client_secret(),
            }
        )
        access_token, refresh_token, expires_at, granted_scopes, token_type = self._parse_token_payload(token_payload, fallback_scopes=oauth_state.scopes)
        if refresh_token is None:
            raise MotiveConnectorError("Motive token response did not include a refresh credential", status=ConnectorStatus.FAILED, code="malformed_response")
        self._credential_store_factory(oauth_state.organization_id).save_tokens(
            organization_slug=oauth_state.organization_slug,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            granted_scopes=granted_scopes,
            token_type=token_type,
        )
        return {
            "organization_id": oauth_state.organization_id,
            "organization_slug": oauth_state.organization_slug,
            "connection_status": "configured_unverified",
            "expires_at": expires_at.isoformat(),
            "granted_scopes": granted_scopes,
            "secrets_exposed": False,
        }

    def access_token_for_request(self, organization_id: str) -> str:
        credential = self._credential_store_factory(organization_id).load_tokens()
        if not _expires_soon(credential.expires_at):
            return credential.access_token
        return self.refresh_access_token(organization_id)

    def refresh_access_token(self, organization_id: str) -> str:
        store = self._credential_store_factory(organization_id)
        credential = store.load_tokens()
        try:
            token_payload = self._token_request(
                {
                    "grant_type": "refresh_token",
                    "refresh_token": credential.refresh_token,
                    "client_id": self.client_id(),
                    "client_secret": self.client_secret(),
                }
            )
        except MotiveConnectorError as exc:
            if exc.code == "invalid_grant" or exc.status == ConnectorStatus.AUTHORIZATION_REQUIRED:
                store.record_failure(
                    status="authorization_required",
                    error_code=exc.code,
                    error_message_sanitized=str(exc),
                    authorization_required=True,
                )
            raise
        access_token, refresh_token, expires_at, granted_scopes, token_type = self._parse_token_payload(
            token_payload,
            fallback_scopes=credential.granted_scopes,
        )
        store.rotate_tokens(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            granted_scopes=granted_scopes,
            token_type=token_type,
        )
        return access_token

    def _consume_state(self, state: str, *, expected_organization_id: str | None) -> _OAuthStateMetadata:
        if not state:
            raise MotiveConnectorError("Motive OAuth state is missing", status=ConnectorStatus.AUTHORIZATION_REQUIRED, code="state_missing")
        now = datetime.now(timezone.utc)
        with SessionLocal.begin() as session:
            oauth_state = session.query(MotiveOAuthState).filter_by(state=state).with_for_update().one_or_none()
            if oauth_state is None:
                raise MotiveConnectorError("Motive OAuth state is invalid", status=ConnectorStatus.AUTHORIZATION_REQUIRED, code="state_missing")
            if expected_organization_id and oauth_state.organization_id != expected_organization_id:
                raise MotiveConnectorError("Motive OAuth state organization mismatch", status=ConnectorStatus.AUTHORIZATION_REQUIRED, code="state_wrong_organization")
            if oauth_state.consumed_at is not None:
                raise MotiveConnectorError("Motive OAuth state was already used", status=ConnectorStatus.AUTHORIZATION_REQUIRED, code="state_reused")
            if _as_utc(oauth_state.expires_at) <= now:
                raise MotiveConnectorError("Motive OAuth state expired", status=ConnectorStatus.AUTHORIZATION_REQUIRED, code="state_expired")
            organization = session.query(Organization).filter(Organization.id == oauth_state.organization_id).one_or_none()
            if organization is None:
                raise MotiveConnectorError("Motive OAuth organization is missing", status=ConnectorStatus.AUTHORIZATION_REQUIRED, code="organization_missing")
            metadata = _OAuthStateMetadata(
                organization_id=oauth_state.organization_id,
                organization_slug=organization.slug,
                redirect_uri=oauth_state.redirect_uri,
                scopes=oauth_state.scopes,
            )
            oauth_state.consumed_at = now
            return metadata

    def _token_request(self, data: dict[str, str]) -> dict[str, Any]:
        last_error: MotiveConnectorError | None = None
        for attempt in range(1, _max_attempts() + 1):
            try:
                response = self._http().post(
                    MOTIVE_TOKEN_URL,
                    data=data,
                    headers={"Accept": "application/json"},
                )
                return self._json_response(response)
            except MotiveConnectorError as exc:
                last_error = exc
                if not exc.retryable or attempt == _max_attempts():
                    raise
                self._sleep(_retry_delay(attempt))
            except httpx.TimeoutException as exc:
                last_error = MotiveConnectorError("Motive OAuth token request timed out", status=ConnectorStatus.FAILED, retryable=True, code="timeout")
                if attempt == _max_attempts():
                    raise last_error from exc
                self._sleep(_retry_delay(attempt))
            except httpx.HTTPError as exc:
                last_error = MotiveConnectorError("Motive OAuth token request failed due to a network error", status=ConnectorStatus.FAILED, retryable=True, code="network_failure")
                if attempt == _max_attempts():
                    raise last_error from exc
                self._sleep(_retry_delay(attempt))
        raise last_error or MotiveConnectorError("Motive OAuth token request failed", status=ConnectorStatus.FAILED)

    def _json_response(self, response: httpx.Response) -> dict[str, Any]:
        if response.status_code == 429:
            raise MotiveConnectorError("Motive request was rate limited", status=ConnectorStatus.RATE_LIMITED, retryable=False, code="rate_limited")
        payload: dict[str, Any] = {}
        if response.content:
            try:
                decoded = response.json()
                if isinstance(decoded, dict):
                    payload = decoded
            except ValueError:
                if response.status_code < 400:
                    raise MotiveConnectorError("Motive returned invalid JSON", status=ConnectorStatus.FAILED, code="malformed_response")
        provider_error = str(payload.get("error") or "")
        if provider_error == "invalid_grant":
            raise MotiveConnectorError("Motive OAuth grant is invalid", status=ConnectorStatus.AUTHORIZATION_REQUIRED, retryable=False, code="invalid_grant")
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
                f"Motive request failed with HTTP {response.status_code}",
                status=ConnectorStatus.FAILED,
                retryable=False,
                code=f"http_{response.status_code}",
            )
        if not payload:
            raise MotiveConnectorError("Motive returned an empty response", status=ConnectorStatus.FAILED, code="malformed_response")
        return payload

    def _parse_token_payload(self, payload: dict[str, Any], *, fallback_scopes: str) -> tuple[str, str | None, datetime, str, str]:
        access_token = payload.get("access_token")
        refresh_token = payload.get("refresh_token")
        if not isinstance(access_token, str) or not access_token:
            raise MotiveConnectorError("Motive token response did not include an access credential", status=ConnectorStatus.FAILED, code="malformed_response")
        expires_in = int(payload.get("expires_in") or 7200)
        scopes = payload.get("scope") or payload.get("scopes") or fallback_scopes
        if isinstance(scopes, list):
            scopes = " ".join(str(scope) for scope in scopes)
        token_type = str(payload.get("token_type") or "Bearer")
        return access_token, refresh_token if isinstance(refresh_token, str) else None, datetime.now(timezone.utc) + timedelta(seconds=expires_in), str(scopes), token_type

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=_timeout_seconds())
        return self._client

    @staticmethod
    def validate_oauth_configuration() -> None:
        missing = [name for name in ("MOTIVE_CLIENT_ID", "MOTIVE_CLIENT_SECRET", "MOTIVE_REDIRECT_URI") if not os.getenv(name)]
        if missing:
            raise MotiveConnectorError("Motive OAuth configuration is incomplete", status=ConnectorStatus.NOT_CONFIGURED, code="oauth_configuration_missing")
        if not os.getenv("POLARIS_MOTIVE_TOKEN_ENCRYPTION_KEY") and not os.getenv("POLARIS_QBO_TOKEN_ENCRYPTION_KEY"):
            raise MotiveConnectorError("Motive token encryption is not configured", status=ConnectorStatus.NOT_CONFIGURED, code="encryption_not_configured")

    @staticmethod
    def client_id() -> str:
        return os.environ["MOTIVE_CLIENT_ID"]

    @staticmethod
    def client_secret() -> str:
        return os.environ["MOTIVE_CLIENT_SECRET"]

    @staticmethod
    def redirect_uri() -> str:
        return os.environ["MOTIVE_REDIRECT_URI"]


class MotiveConnector(BaseConnector):
    """Expose safe Motive status and one narrow OAuth read-only verification call."""

    def __init__(
        self,
        *,
        http_client: httpx.Client | None = None,
        credential_store: MotiveCredentialStore | None = None,
        oauth_service: MotiveOAuthService | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        super().__init__(name="motive")
        self._client = http_client
        self._credential_store = credential_store
        self._sleep = sleep
        self._oauth_service = oauth_service or MotiveOAuthService(http_client=http_client, sleep=sleep)

    def validate_configuration(self) -> None:
        MotiveOAuthService.validate_oauth_configuration()
        try:
            metadata = self._store().metadata()
        except MotiveCredentialError as exc:
            raise MotiveConnectorError(str(exc), status=ConnectorStatus.NOT_CONFIGURED) from exc
        if not metadata.get("token_present"):
            raise MotiveConnectorError("Motive OAuth credential is not configured", status=ConnectorStatus.NOT_CONFIGURED)

    def authenticate(self) -> None:
        self.validate_configuration()
        self._oauth_service.access_token_for_request(self._store().organization_id)

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
            errors=["Motive broad synchronization is deferred; use OAuth verification only."],
        )

    def disconnect(self) -> None:
        self._store().delete()

    def safe_status(self) -> dict[str, Any]:
        store = self._store_or_none()
        metadata = store.metadata() if store else {
            "provider": "motive",
            "authentication_method": "oauth2",
            "connection_status": "not_configured",
            "token_present": False,
            "authorization_required": True,
            "secrets_exposed": False,
        }
        return {
            **metadata,
            "read_only": True,
            "production_sync_enabled": False,
            "verification_endpoint": MOTIVE_VERIFICATION_ENDPOINT,
            "verified_resources": ["companies", "vehicles", "vehicle_utilization", "driver_utilization", "ifta_summary"],
            "deferred_resources": ["driver_list", "hos", "safety", "dvir", "fault_codes", "trips", "maintenance", "fuel_purchases", "webhooks"],
            "secrets_exposed": False,
        }

    def verify_connection(self) -> dict[str, Any]:
        try:
            access_token = self._oauth_service.access_token_for_request(self._store().organization_id)
            payload = self._request_company_details(access_token)
            company = _company_metadata(payload)
            verified_at = datetime.now(timezone.utc)
            self._store().record_verification_success(
                verified_at=verified_at,
                provider_company_id=company.get("provider_company_id"),
                provider_company_name=company.get("provider_company_name"),
            )
            return {
                "connector": self.name,
                "status": "connected",
                "verified_at": verified_at.isoformat(),
                "endpoint": MOTIVE_VERIFICATION_ENDPOINT,
                "request": {"method": "GET", "path": MOTIVE_VERIFICATION_ENDPOINT, "params": {}},
                "records_read": 1 if company else 0,
                "records_written": 0,
                "provider_company_id": company.get("provider_company_id"),
                "provider_company_name": company.get("provider_company_name"),
                "production_certified": False,
                "secrets_exposed": False,
            }
        except MotiveConnectorError as exc:
            store = self._store_or_none()
            if store:
                store.record_failure(
                    status=exc.status.value,
                    error_code=exc.code,
                    error_message_sanitized=str(exc),
                    authorization_required=exc.status == ConnectorStatus.AUTHORIZATION_REQUIRED,
                )
            raise

    def _request_company_details(self, access_token: str) -> dict[str, Any]:
        last_error: MotiveConnectorError | None = None
        for attempt in range(1, _max_attempts() + 1):
            try:
                response = self._http().get(
                    f"{self._base_url()}{MOTIVE_VERIFICATION_ENDPOINT}",
                    headers={"Accept": "application/json", "Authorization": f"Bearer {access_token}"},
                )
                return self._json_response(response)
            except MotiveConnectorError as exc:
                last_error = exc
                if not exc.retryable or attempt == _max_attempts():
                    raise
                self._sleep(_retry_delay(attempt))
            except httpx.TimeoutException as exc:
                last_error = MotiveConnectorError("Motive verification timed out", status=ConnectorStatus.FAILED, retryable=True, code="timeout")
                if attempt == _max_attempts():
                    raise last_error from exc
                self._sleep(_retry_delay(attempt))
            except httpx.HTTPError as exc:
                last_error = MotiveConnectorError("Motive verification failed due to a network error", status=ConnectorStatus.FAILED, retryable=True, code="network_failure")
                if attempt == _max_attempts():
                    raise last_error from exc
                self._sleep(_retry_delay(attempt))
        raise last_error or MotiveConnectorError("Motive verification failed", status=ConnectorStatus.FAILED)

    def _json_response(self, response: httpx.Response) -> dict[str, Any]:
        return MotiveOAuthService(http_client=self._http())._json_response(response)

    def _store(self) -> MotiveCredentialStore:
        if self._credential_store is None:
            raise MotiveConnectorError("Motive organization context is required", status=ConnectorStatus.AUTHORIZATION_REQUIRED)
        return self._credential_store

    def _store_or_none(self) -> MotiveCredentialStore | None:
        return self._credential_store

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=_timeout_seconds())
        return self._client

    @staticmethod
    def _base_url() -> str:
        return os.getenv("POLARIS_MOTIVE_API_BASE_URL", MOTIVE_API_BASE_URL).rstrip("/")


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
        return "Motive OAuth credential is not configured."
    if value == "configured_unverified":
        return "Motive OAuth credential is configured but not verified."
    if value == "connected":
        return "Motive OAuth credential passed limited read-only verification."
    if value == "rate_limited":
        return "Motive verification is rate limited; retry timing is not assumed."
    if value == "authorization_required":
        return "Motive authorization is required."
    return "Motive connector status is available."


def _company_metadata(payload: dict[str, Any]) -> dict[str, str]:
    company: Any = payload.get("company") or payload.get("data") or payload
    if isinstance(company, list):
        company = company[0] if company else {}
    if not isinstance(company, dict):
        return {}
    provider_company_id = company.get("id") or company.get("company_id")
    provider_company_name = company.get("name") or company.get("company_name")
    result: dict[str, str] = {}
    if provider_company_id is not None:
        result["provider_company_id"] = str(provider_company_id)
    if isinstance(provider_company_name, str) and provider_company_name:
        result["provider_company_name"] = provider_company_name
    return result


def _expires_soon(expires_at: datetime) -> bool:
    return _as_utc(expires_at) <= datetime.now(timezone.utc) + timedelta(seconds=_TOKEN_REFRESH_SKEW_SECONDS)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _timeout_seconds() -> float:
    return float(os.getenv("POLARIS_MOTIVE_REQUEST_TIMEOUT_SECONDS", "10"))


def _max_attempts() -> int:
    return min(max(int(os.getenv("POLARIS_MOTIVE_MAX_ATTEMPTS", "2")), 1), 2)


def _retry_delay(attempt: int) -> float:
    return float(os.getenv("POLARIS_MOTIVE_RETRY_BASE_SECONDS", "0.25")) * attempt


def _sanitize(message: str) -> str:
    sanitized = " ".join(str(message).split())
    for marker in ("access_token", "refresh_token", "authorization", "bearer", "client_secret", "code", "token", "secret"):
        sanitized = sanitized.replace(marker, "credential")
        sanitized = sanitized.replace(marker.upper(), "CREDENTIAL")
    return sanitized[:500]
