"""Polaris-owned OAuth authorization flow for Microsoft Outlook."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import httpx
from sqlalchemy import update

from app.connectors.outlook_credentials import OutlookCredentialStore, OutlookOAuthState
from app.database.database import SessionLocal
from app.organizations.models import Organization

AUTHORITY_TEMPLATE = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0"
GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
READ_ONLY_SCOPE = "openid profile email offline_access https://graph.microsoft.com/Mail.Read"
STATE_TTL_SECONDS = 600


class OutlookOAuthError(RuntimeError):
    """Safe OAuth error that excludes credentials, authorization codes, and tokens."""


@dataclass(frozen=True)
class OutlookOAuthTokens:
    access_token: str
    refresh_token: str
    expires_in: int
    scope: str
    microsoft_tenant_id: str | None = None


@dataclass(frozen=True)
class OutlookMailboxIdentity:
    microsoft_tenant_id: str
    mailbox_user_id: str
    mailbox_address: str
    display_name: str | None = None


@dataclass(frozen=True)
class OutlookOAuthContext:
    organization_id: str
    identity_id: str
    mailbox_address: str


class OutlookOAuthService:
    """Create Microsoft authorization requests, validate callbacks, and persist tokens."""

    def __init__(self, *, http_client: httpx.Client | None = None) -> None:
        self._client = http_client

    def authorization_url(self, *, organization_id: str, identity_id: str) -> str:
        self._validate_configuration()
        state = self._create_state(organization_id=organization_id, identity_id=identity_id)
        return self._authorization_endpoint() + "?" + urlencode(
            {
                "client_id": os.environ["POLARIS_OUTLOOK_CLIENT_ID"],
                "response_type": "code",
                "redirect_uri": os.environ["POLARIS_OUTLOOK_REDIRECT_URI"],
                "response_mode": "query",
                "scope": self._scope(),
                "state": state,
            }
        )

    def complete_authorization(
        self,
        *,
        code: str,
        state: str,
        expected_organization_id: str | None = None,
        expected_identity_id: str | None = None,
    ) -> OutlookOAuthContext:
        self._validate_configuration()
        context = self._consume_state(
            state,
            expected_organization_id=expected_organization_id,
            expected_identity_id=expected_identity_id,
        )
        if not code:
            raise OutlookOAuthError("Outlook callback is missing required parameters")
        tokens = self._exchange_code(code)
        mailbox = self._mailbox_identity(tokens.access_token, fallback_tenant_id=tokens.microsoft_tenant_id)
        org_slug = self._organization_slug(context.organization_id)
        OutlookCredentialStore(context.organization_id).save(
            organization_slug=org_slug,
            microsoft_tenant_id=mailbox.microsoft_tenant_id,
            mailbox_user_id=mailbox.mailbox_user_id,
            mailbox_address=mailbox.mailbox_address,
            refresh_token=tokens.refresh_token,
            scopes=tokens.scope,
        )
        return OutlookOAuthContext(
            organization_id=context.organization_id,
            identity_id=context.identity_id,
            mailbox_address=mailbox.mailbox_address,
        )

    def _exchange_code(self, code: str) -> OutlookOAuthTokens:
        payload = self._token_request(
            {
                "client_id": os.environ["POLARIS_OUTLOOK_CLIENT_ID"],
                "client_secret": os.environ["POLARIS_OUTLOOK_CLIENT_SECRET"],
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": os.environ["POLARIS_OUTLOOK_REDIRECT_URI"],
                "scope": self._scope(),
            }
        )
        access_token = payload.get("access_token")
        refresh_token = payload.get("refresh_token")
        if not isinstance(access_token, str) or not isinstance(refresh_token, str):
            raise OutlookOAuthError("Outlook token exchange returned incomplete tokens")
        return OutlookOAuthTokens(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=int(payload.get("expires_in", 3600)),
            scope=str(payload.get("scope") or self._scope()),
            microsoft_tenant_id=_tenant_from_id_token(str(payload.get("id_token") or "")),
        )

    def refresh_access_token(self, *, organization_id: str) -> tuple[str, int]:
        self._validate_configuration()
        store = OutlookCredentialStore(organization_id)
        credential = store.load_credential()
        payload = self._token_request(
            {
                "client_id": os.environ["POLARIS_OUTLOOK_CLIENT_ID"],
                "client_secret": os.environ["POLARIS_OUTLOOK_CLIENT_SECRET"],
                "grant_type": "refresh_token",
                "refresh_token": credential.refresh_token,
                "scope": credential.scopes or self._scope(),
            }
        )
        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            store.record_refresh_failure("Outlook token refresh returned no access token", reauthorization_required=True)
            raise OutlookOAuthError("Outlook token refresh returned no access token")
        rotated = payload.get("refresh_token")
        if isinstance(rotated, str) and rotated:
            store.rotate_refresh_token(refresh_token=rotated, scopes=str(payload.get("scope") or credential.scopes))
        else:
            store.update_metadata(last_refresh_at=datetime.now(timezone.utc), last_refresh_status="success")
        return access_token, int(payload.get("expires_in", 3600))

    def _token_request(self, form: dict[str, str]) -> dict[str, Any]:
        try:
            response = self._http().post(
                self._token_endpoint(),
                data=form,
                headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
            )
        except httpx.TimeoutException as exc:
            raise OutlookOAuthError("Outlook token request timed out") from exc
        except httpx.HTTPError as exc:
            raise OutlookOAuthError("Outlook token request failed") from exc
        if response.status_code >= 400:
            raise OutlookOAuthError(f"Outlook token request failed with HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise OutlookOAuthError("Outlook token request returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise OutlookOAuthError("Outlook token request returned an unexpected response")
        return payload

    def _mailbox_identity(self, access_token: str, *, fallback_tenant_id: str | None = None) -> OutlookMailboxIdentity:
        try:
            response = self._http().get(
                f"{self._graph_base_url()}/me",
                headers={"Accept": "application/json", "Authorization": f"Bearer {access_token}"},
                params={"$select": "id,displayName,mail,userPrincipalName"},
            )
        except httpx.HTTPError as exc:
            raise OutlookOAuthError("Outlook mailbox identity verification failed") from exc
        if response.status_code >= 400:
            raise OutlookOAuthError(f"Outlook mailbox identity verification failed with HTTP {response.status_code}")
        payload = response.json()
        if not isinstance(payload, dict):
            raise OutlookOAuthError("Outlook mailbox identity response was malformed")
        mailbox_user_id = str(payload.get("id") or "").strip()
        mailbox_address = str(payload.get("mail") or payload.get("userPrincipalName") or "").strip().lower()
        if not mailbox_user_id or not mailbox_address:
            raise OutlookOAuthError("Outlook mailbox identity is incomplete")
        tenant_id = fallback_tenant_id or self._tenant()
        return OutlookMailboxIdentity(
            microsoft_tenant_id=tenant_id,
            mailbox_user_id=mailbox_user_id,
            mailbox_address=mailbox_address,
            display_name=str(payload.get("displayName") or "") or None,
        )

    def _create_state(self, *, organization_id: str, identity_id: str) -> str:
        timestamp = str(int(time.time()))
        nonce = secrets.token_urlsafe(24)
        body = f"{timestamp}.{nonce}"
        signature = hmac.new(self._state_secret().encode(), body.encode(), hashlib.sha256).hexdigest()
        state = f"{body}.{signature}"
        now = datetime.now(timezone.utc)
        with SessionLocal.begin() as session:
            session.add(
                OutlookOAuthState(
                    state=state,
                    organization_id=organization_id,
                    identity_id=identity_id,
                    nonce=nonce,
                    created_at=now,
                    expires_at=now + timedelta(seconds=STATE_TTL_SECONDS),
                )
            )
        return state

    def _consume_state(
        self,
        state: str,
        *,
        expected_organization_id: str | None = None,
        expected_identity_id: str | None = None,
    ) -> OutlookOAuthContext:
        self._validate_state_signature(state)
        now = datetime.now(timezone.utc)
        with SessionLocal.begin() as session:
            result = session.execute(
                update(OutlookOAuthState)
                .where(
                    OutlookOAuthState.state == state,
                    OutlookOAuthState.consumed_at.is_(None),
                    OutlookOAuthState.expires_at > now,
                    *([OutlookOAuthState.organization_id == expected_organization_id] if expected_organization_id else []),
                    *([OutlookOAuthState.identity_id == expected_identity_id] if expected_identity_id else []),
                )
                .values(consumed_at=now)
            )
            if result.rowcount != 1:
                record = session.get(OutlookOAuthState, state)
                if record is None:
                    raise OutlookOAuthError("Outlook OAuth state is unknown")
                if expected_organization_id and record.organization_id != expected_organization_id:
                    raise OutlookOAuthError("Outlook OAuth state organization does not match")
                if expected_identity_id and record.identity_id != expected_identity_id:
                    raise OutlookOAuthError("Outlook OAuth state principal does not match")
                if record.consumed_at is not None:
                    raise OutlookOAuthError("Outlook OAuth state has already been used")
                expires_at = record.expires_at
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)
                if expires_at <= now:
                    raise OutlookOAuthError("Outlook OAuth state has expired")
                raise OutlookOAuthError("Outlook OAuth state could not be consumed")
            record = session.get(OutlookOAuthState, state)
            return OutlookOAuthContext(organization_id=record.organization_id, identity_id=record.identity_id, mailbox_address="")

    def _validate_state_signature(self, state: str) -> None:
        try:
            timestamp_text, nonce, signature = state.split(".", 2)
            timestamp = int(timestamp_text)
        except (ValueError, AttributeError) as exc:
            raise OutlookOAuthError("Outlook OAuth state is invalid") from exc
        body = f"{timestamp_text}.{nonce}"
        expected = hmac.new(self._state_secret().encode(), body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise OutlookOAuthError("Outlook OAuth state validation failed")
        if abs(int(time.time()) - timestamp) > STATE_TTL_SECONDS:
            raise OutlookOAuthError("Outlook OAuth state has expired")

    def _organization_slug(self, organization_id: str) -> str:
        with SessionLocal() as session:
            organization = session.get(Organization, organization_id)
            slug = organization.slug.strip() if organization and organization.slug else ""
        if not slug:
            raise OutlookOAuthError("Outlook organization context is invalid")
        return slug

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=float(os.getenv("POLARIS_OUTLOOK_REQUEST_TIMEOUT_SECONDS", "20")))
        return self._client

    @staticmethod
    def _tenant() -> str:
        return os.getenv("POLARIS_OUTLOOK_TENANT", "organizations").strip() or "organizations"

    def _authority_base(self) -> str:
        configured = os.getenv("POLARIS_OUTLOOK_AUTHORITY_BASE_URL")
        if configured:
            return configured.rstrip("/")
        return AUTHORITY_TEMPLATE.format(tenant=self._tenant())

    def _authorization_endpoint(self) -> str:
        return f"{self._authority_base()}/authorize"

    def _token_endpoint(self) -> str:
        return f"{self._authority_base()}/token"

    @staticmethod
    def _graph_base_url() -> str:
        return os.getenv("POLARIS_OUTLOOK_GRAPH_BASE_URL", GRAPH_BASE_URL).rstrip("/")

    @staticmethod
    def _scope() -> str:
        return os.getenv("POLARIS_OUTLOOK_SCOPES", READ_ONLY_SCOPE).strip() or READ_ONLY_SCOPE

    @staticmethod
    def _state_secret() -> str:
        secret = os.getenv("POLARIS_OUTLOOK_OAUTH_STATE_SECRET")
        if not secret or len(secret) < 32:
            raise OutlookOAuthError("Outlook OAuth state signing is not configured")
        return secret

    @classmethod
    def _validate_configuration(cls) -> None:
        missing = [
            name
            for name in (
                "POLARIS_OUTLOOK_CLIENT_ID",
                "POLARIS_OUTLOOK_CLIENT_SECRET",
                "POLARIS_OUTLOOK_REDIRECT_URI",
                "POLARIS_OUTLOOK_OAUTH_STATE_SECRET",
                "POLARIS_OUTLOOK_TOKEN_ENCRYPTION_KEY",
            )
            if not os.getenv(name)
        ]
        if missing:
            raise OutlookOAuthError("Outlook OAuth is not configured. Missing environment variables: " + ", ".join(missing))
        scopes = set(cls._scope().split())
        forbidden = {scope for scope in scopes if "Mail.ReadWrite" in scope or "Mail.Send" in scope}
        if forbidden:
            raise OutlookOAuthError("Outlook OAuth scopes must be read-only")


def _tenant_from_id_token(id_token: str) -> str | None:
    try:
        _header, payload, _signature = id_token.split(".", 2)
        payload += "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload.encode()).decode())
    except Exception:
        return None
    tenant = data.get("tid")
    return str(tenant) if tenant else None
