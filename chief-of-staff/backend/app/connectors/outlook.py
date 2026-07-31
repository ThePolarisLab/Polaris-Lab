"""Read-only Microsoft Graph Outlook connector for Polaris."""

from __future__ import annotations

import os
import re
import threading
import time
from collections.abc import Callable, Sequence
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import httpx

from app.connectors.base import BaseConnector
from app.connectors.models import ConnectorHealth, ConnectorStatus, SyncResult
from app.connectors.outlook_credentials import OutlookCredentialError, OutlookCredentialStore
from app.connectors.outlook_oauth import GRAPH_BASE_URL, OutlookOAuthError, OutlookOAuthService

_REAUTH_CODES = {400, 401, 403}
_ORG_LOCKS: dict[str, threading.Lock] = {}
_ORG_LOCKS_GUARD = threading.Lock()


class OutlookConnectorError(RuntimeError):
    """Safe connector error that never includes Microsoft tokens or raw messages."""

    def __init__(self, message: str, *, status: ConnectorStatus = ConnectorStatus.DEGRADED, retryable: bool = False) -> None:
        super().__init__(_redact(message))
        self.status = status
        self.retryable = retryable


class OutlookConnector(BaseConnector):
    """Read Microsoft Outlook data without mutating a mailbox."""

    def __init__(
        self,
        *,
        http_client: httpx.Client | None = None,
        credential_store: OutlookCredentialStore | None = None,
        oauth_service: OutlookOAuthService | None = None,
        now: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        super().__init__(name="outlook")
        self._client = http_client
        self._credential_store = credential_store
        self._oauth_service = oauth_service
        self._now = now
        self._sleep = sleep
        self._access_token: str | None = None
        self._access_token_expires_at = 0.0
        self._refresh_lock = threading.Lock()

    def validate_configuration(self) -> None:
        missing = [name for name in self._required_env() if not os.getenv(name)]
        if missing:
            raise OutlookConnectorError(
                "Outlook is not configured. Missing environment variables: " + ", ".join(missing),
                status=ConnectorStatus.NOT_CONFIGURED,
            )
        scopes = set(os.getenv("POLARIS_OUTLOOK_SCOPES", "openid profile email offline_access https://graph.microsoft.com/Mail.Read").split())
        if any("Mail.ReadWrite" in scope or "Mail.Send" in scope for scope in scopes):
            raise OutlookConnectorError("Outlook scopes must remain read-only", status=ConnectorStatus.CONFIGURATION_ERROR)
        try:
            self._store().load_credential()
        except OutlookCredentialError as exc:
            raise OutlookConnectorError(str(exc), status=ConnectorStatus.AUTHORIZATION_REQUIRED) from exc

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
        try:
            metadata = self._store_or_none().metadata() if self._store_or_none() else {}
            if not metadata.get("authorized"):
                raise OutlookConnectorError("Outlook authorization is required", status=ConnectorStatus.AUTHORIZATION_REQUIRED)
            latency_ms = (datetime.now(timezone.utc) - started).total_seconds() * 1000
            status = ConnectorStatus(metadata.get("connector_health_status") or ConnectorStatus.CONNECTED_UNVERIFIED.value)
            if status == ConnectorStatus.CONNECTED_UNVERIFIED:
                status = ConnectorStatus.HEALTHY
            return ConnectorHealth(
                name=self.name,
                status=status,
                checked_at=datetime.now(timezone.utc),
                latency_ms=round(latency_ms, 2),
                last_sync_at=_parse_datetime(metadata.get("last_successful_sync_at")),
                message=_safe_mailbox_message(metadata),
                details=self.safe_status(),
            )
        except OutlookConnectorError as exc:
            return ConnectorHealth(
                name=self.name,
                status=exc.status,
                message=str(exc),
                details=self.safe_status(),
            )

    def discover(self) -> Sequence[str]:
        return ("mailbox", "folders", "messages", "attachments", "delta", "attention")

    def sync(self) -> SyncResult:
        from app.services.outlook_sync import OutlookSyncService

        return OutlookSyncService(connector=self, organization_id=self._store().organization_id).sync(mode="incremental")

    def disconnect(self) -> None:
        self._access_token = None
        self._access_token_expires_at = 0.0
        self._store().delete()

    def mailbox_identity(self) -> dict[str, Any]:
        return self._request_json("GET", "/me", operation="mailbox identity", params={"$select": "id,displayName,mail,userPrincipalName"})

    def list_folders(self, *, url: str | None = None) -> dict[str, Any]:
        if url:
            return self._request_absolute_json("GET", url, operation="mail folder page")
        return self._request_json(
            "GET",
            "/me/mailFolders",
            operation="mail folder list",
            params={"$top": "100", "$select": "id,displayName,parentFolderId,childFolderCount,totalItemCount,unreadItemCount"},
        )

    def list_child_folders(self, folder_id: str, *, url: str | None = None) -> dict[str, Any]:
        if url:
            return self._request_absolute_json("GET", url, operation="child folder page")
        return self._request_json(
            "GET",
            f"/me/mailFolders/{_quote_segment(folder_id)}/childFolders",
            operation="child folder list",
            params={"$top": "100", "$select": "id,displayName,parentFolderId,childFolderCount,totalItemCount,unreadItemCount"},
        )

    def list_messages(self, folder_id: str, *, url: str | None = None, since_iso: str | None = None) -> dict[str, Any]:
        if url:
            return self._request_absolute_json("GET", url, operation="message page")
        params: dict[str, str] = {
            "$top": str(self._page_size()),
            "$orderby": "receivedDateTime desc",
            "$select": _message_select(),
        }
        if since_iso:
            params["$filter"] = f"receivedDateTime ge {since_iso}"
        return self._request_json(
            "GET",
            f"/me/mailFolders/{_quote_segment(folder_id)}/messages",
            operation="message list",
            params=params,
            prefer_text_body=True,
        )

    def delta_messages(self, folder_id: str, *, delta_link: str | None = None) -> dict[str, Any]:
        if delta_link:
            return self._request_absolute_json("GET", delta_link, operation="message delta", prefer_text_body=True)
        return self._request_json(
            "GET",
            f"/me/mailFolders/{_quote_segment(folder_id)}/messages/delta",
            operation="message delta",
            params={"$top": str(self._page_size()), "$select": _message_select()},
            prefer_text_body=True,
        )

    def list_attachments(self, message_id: str, *, url: str | None = None) -> dict[str, Any]:
        if url:
            return self._request_absolute_json("GET", url, operation="attachment page")
        return self._request_json(
            "GET",
            f"/me/messages/{_quote_segment(message_id)}/attachments",
            operation="attachment metadata",
            params={"$top": "100", "$select": "id,name,contentType,size,isInline,contentId"},
        )

    def safe_status(self) -> dict[str, Any]:
        store = self._store_or_none()
        metadata = store.metadata() if store else {"authorized": False}
        return {
            "organization_id": metadata.get("organization_id") or (store.organization_id if store else None),
            "authorization_status": "authorized" if metadata.get("authorized") else "authorization_required",
            "mailbox_address": metadata.get("mailbox_address"),
            "microsoft_tenant_status": metadata.get("microsoft_tenant_status", "absent"),
            "granted_scopes": _safe_scopes(metadata.get("granted_scopes")),
            "read_only": True,
            "last_successful_sync_time": metadata.get("last_successful_sync_at"),
            "last_safe_error_summary": metadata.get("last_error_summary"),
            "reauthorization_required": bool(metadata.get("reauthorization_required", False)),
            "secrets_exposed": False,
        }

    @contextmanager
    def organization_sync_lock(self):
        organization_id = self._store().organization_id
        with _ORG_LOCKS_GUARD:
            lock = _ORG_LOCKS.setdefault(organization_id, threading.Lock())
        acquired = lock.acquire(blocking=False)
        if not acquired:
            raise OutlookConnectorError(
                "Outlook synchronization is already running for this organization",
                status=ConnectorStatus.DEGRADED,
            )
        try:
            yield
        finally:
            lock.release()

    def _refresh_access_token(self) -> None:
        try:
            access_token, expires_in = self._oauth().refresh_access_token(organization_id=self._store().organization_id)
        except (OutlookCredentialError, OutlookOAuthError) as exc:
            raise OutlookConnectorError(str(exc), status=ConnectorStatus.REAUTHORIZATION_REQUIRED) from exc
        self._access_token = access_token
        self._access_token_expires_at = self._now() + expires_in

    def _request_json(self, method: str, path: str, *, operation: str, params: dict[str, str] | None = None, prefer_text_body: bool = False) -> dict[str, Any]:
        return self._request_absolute_json(method, f"{self._graph_base_url()}{path}", operation=operation, params=params, prefer_text_body=prefer_text_body)

    def _request_absolute_json(self, method: str, url: str, *, operation: str, params: dict[str, str] | None = None, prefer_text_body: bool = False) -> dict[str, Any]:
        safe_url = self._validated_graph_url(url, operation)
        last_error: OutlookConnectorError | None = None
        for attempt in range(1, self._max_attempts() + 1):
            self.authenticate()
            headers = {
                "Accept": "application/json",
                "Authorization": f"Bearer {self._access_token}",
                "X-Polaris-Correlation": _correlation_id(),
            }
            if prefer_text_body:
                headers["Prefer"] = 'outlook.body-content-type="text"'
            try:
                response = self._http().request(method, safe_url, params=params, headers=headers)
                if response.status_code == 401 and attempt < self._max_attempts():
                    self._access_token = None
                    self._refresh_access_token()
                    continue
                return self._json_response(response, operation)
            except OutlookConnectorError as exc:
                last_error = exc
                if not exc.retryable or attempt == self._max_attempts():
                    raise
                self._sleep(self._retry_delay(attempt))
            except httpx.TimeoutException as exc:
                last_error = OutlookConnectorError(f"Outlook {operation} timed out", status=ConnectorStatus.DEGRADED, retryable=True)
                if attempt == self._max_attempts():
                    raise last_error from exc
                self._sleep(self._retry_delay(attempt))
            except httpx.HTTPError as exc:
                last_error = OutlookConnectorError(f"Outlook {operation} failed", status=ConnectorStatus.DEGRADED, retryable=True)
                if attempt == self._max_attempts():
                    raise last_error from exc
                self._sleep(self._retry_delay(attempt))
        raise last_error or OutlookConnectorError(f"Outlook {operation} failed")

    def _validated_graph_url(self, url: str, operation: str) -> str:
        parsed = urlparse(url)
        base = urlparse(self._graph_base_url())
        base_path = base.path.rstrip("/")
        if parsed.scheme != base.scheme or parsed.netloc != base.netloc:
            raise OutlookConnectorError(
                f"Outlook {operation} returned an unsafe provider continuation URL",
                status=ConnectorStatus.DEGRADED,
            )
        if base_path and not (parsed.path == base_path or parsed.path.startswith(base_path + "/")):
            raise OutlookConnectorError(
                f"Outlook {operation} returned an unsafe provider continuation path",
                status=ConnectorStatus.DEGRADED,
            )
        return url

    def _json_response(self, response: httpx.Response, operation: str) -> dict[str, Any]:
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    self._sleep(min(float(retry_after), 30.0))
                except ValueError:
                    pass
            raise OutlookConnectorError(f"Outlook {operation} is rate limited", status=ConnectorStatus.RATE_LIMITED, retryable=True)
        if response.status_code in _REAUTH_CODES:
            message = f"Outlook {operation} authorization failed with HTTP {response.status_code}"
            self._store().record_refresh_failure(message, reauthorization_required=response.status_code in {400, 401})
            raise OutlookConnectorError(message, status=ConnectorStatus.REAUTHORIZATION_REQUIRED)
        if response.status_code >= 500:
            raise OutlookConnectorError(f"Outlook {operation} failed with HTTP {response.status_code}", status=ConnectorStatus.DEGRADED, retryable=True)
        if response.status_code >= 400:
            raise OutlookConnectorError(f"Outlook {operation} failed with HTTP {response.status_code}", status=ConnectorStatus.DEGRADED)
        try:
            payload = response.json()
        except ValueError as exc:
            raise OutlookConnectorError(f"Outlook {operation} returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise OutlookConnectorError(f"Outlook {operation} returned an unexpected response")
        return payload

    def _store(self) -> OutlookCredentialStore:
        if self._credential_store is None:
            raise OutlookConnectorError("Outlook organization context is required", status=ConnectorStatus.AUTHORIZATION_REQUIRED)
        return self._credential_store

    def _store_or_none(self) -> OutlookCredentialStore | None:
        return self._credential_store

    def _oauth(self) -> OutlookOAuthService:
        if self._oauth_service is None:
            self._oauth_service = OutlookOAuthService(http_client=self._http())
        return self._oauth_service

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=self._timeout_seconds())
        return self._client

    @staticmethod
    def _required_env() -> tuple[str, ...]:
        return (
            "POLARIS_OUTLOOK_CLIENT_ID",
            "POLARIS_OUTLOOK_CLIENT_SECRET",
            "POLARIS_OUTLOOK_REDIRECT_URI",
            "POLARIS_OUTLOOK_OAUTH_STATE_SECRET",
            "POLARIS_OUTLOOK_TOKEN_ENCRYPTION_KEY",
        )

    @staticmethod
    def _graph_base_url() -> str:
        return os.getenv("POLARIS_OUTLOOK_GRAPH_BASE_URL", GRAPH_BASE_URL).rstrip("/")

    @staticmethod
    def _timeout_seconds() -> float:
        return float(os.getenv("POLARIS_OUTLOOK_REQUEST_TIMEOUT_SECONDS", "20"))

    @staticmethod
    def _max_attempts() -> int:
        return max(1, int(os.getenv("POLARIS_OUTLOOK_MAX_ATTEMPTS", "3")))

    @staticmethod
    def _retry_delay(attempt: int) -> float:
        base = float(os.getenv("POLARIS_OUTLOOK_RETRY_BASE_SECONDS", "0.25"))
        return base * (2 ** (attempt - 1))

    @staticmethod
    def _page_size() -> int:
        return min(max(int(os.getenv("POLARIS_OUTLOOK_PAGE_SIZE", "50")), 1), 200)


def _message_select() -> str:
    return ",".join(
        [
            "id",
            "conversationId",
            "internetMessageId",
            "parentFolderId",
            "subject",
            "sender",
            "replyTo",
            "toRecipients",
            "ccRecipients",
            "bccRecipients",
            "receivedDateTime",
            "sentDateTime",
            "createdDateTime",
            "lastModifiedDateTime",
            "importance",
            "categories",
            "flag",
            "isRead",
            "isDraft",
            "hasAttachments",
            "body",
            "webLink",
        ]
    )


def _safe_mailbox_message(metadata: dict[str, Any]) -> str:
    mailbox = metadata.get("mailbox_address")
    return f"Connected to {mailbox}." if mailbox else "Outlook connection metadata is available."


def _safe_scopes(value: Any) -> list[str]:
    scopes = value if isinstance(value, list) else []
    return [scope for scope in scopes if "secret" not in str(scope).lower() and "token" not in str(scope).lower()]


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _quote_segment(value: str) -> str:
    from urllib.parse import quote

    return quote(value, safe="")


def _correlation_id() -> str:
    return f"outlook-{int(time.time() * 1000)}"


def _redact(value: str) -> str:
    redacted = re.sub(
        r"(?i)\b(access_token|refresh_token|client_secret|authorization_code|code|state)\s*[:=]\s*[^\s,;]+",
        lambda match: f"{match.group(1)}=[REDACTED]",
        value,
    )
    redacted = re.sub(r"(?i)\bAuthorization\s*[:=]\s*Bearer\s+[^\s,;]+", "Authorization=Bearer [REDACTED]", redacted)
    redacted = re.sub(r"(?i)\bBearer\s+[^\s,;]+", "Bearer [REDACTED]", redacted)
    return redacted
