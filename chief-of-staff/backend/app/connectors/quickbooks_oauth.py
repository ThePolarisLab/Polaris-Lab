"""Polaris-owned OAuth authorization flow for QuickBooks Online."""

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
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.connectors.quickbooks_credentials import (
    QuickBooksCredentialStore,
    QuickBooksOAuthState,
)
from app.database.database import SessionLocal

AUTHORIZATION_URL = "https://appcenter.intuit.com/connect/oauth2"
TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
ACCOUNTING_SCOPE = "com.intuit.quickbooks.accounting"
STATE_TTL_SECONDS = 600


class QuickBooksOAuthError(RuntimeError):
    """Safe OAuth error that excludes credentials and authorization codes."""


@dataclass(frozen=True)
class QuickBooksOAuthTokens:
    access_token: str
    refresh_token: str
    expires_in: int
    refresh_token_expires_in: int | None
    scope: str


@dataclass(frozen=True)
class QuickBooksOAuthContext:
    organization_id: str
    identity_id: str
    organization_slug: str


class QuickBooksOAuthService:
    """Create authorization requests, validate callbacks, and persist tokens."""

    def __init__(self, store: QuickBooksCredentialStore | None = None) -> None:
        self.store = store or QuickBooksCredentialStore()

    def authorization_url(
        self,
        *,
        organization_id: str,
        identity_id: str,
        organization_slug: str | None = None,
    ) -> str:
        self._validate_configuration()
        state = self._create_state(
            organization_id=organization_id,
            identity_id=identity_id,
            organization_slug=organization_slug or os.getenv("POLARIS_ORGANIZATION_SLUG", "mor-logistics"),
        )
        return AUTHORIZATION_URL + "?" + urlencode(
            {
                "client_id": os.environ["POLARIS_QBO_CLIENT_ID"],
                "response_type": "code",
                "scope": ACCOUNTING_SCOPE,
                "redirect_uri": os.environ["POLARIS_QBO_REDIRECT_URI"],
                "state": state,
            }
        )

    def complete_authorization(self, *, code: str, realm_id: str, state: str) -> QuickBooksOAuthContext:
        self._validate_configuration()
        context = self._consume_state(state)
        if not code or not realm_id:
            raise QuickBooksOAuthError("QuickBooks callback is missing required parameters")
        tokens = self._exchange_code(code)
        QuickBooksCredentialStore(context.organization_slug).save(
            realm_id=realm_id,
            refresh_token=tokens.refresh_token,
            scopes=tokens.scope or ACCOUNTING_SCOPE,
        )
        return context

    def _exchange_code(self, code: str) -> QuickBooksOAuthTokens:
        payload = self._token_request(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": os.environ["POLARIS_QBO_REDIRECT_URI"],
            }
        )
        access_token = payload.get("access_token")
        refresh_token = payload.get("refresh_token")
        if not isinstance(access_token, str) or not isinstance(refresh_token, str):
            raise QuickBooksOAuthError("QuickBooks token exchange returned incomplete tokens")
        return QuickBooksOAuthTokens(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=int(payload.get("expires_in", 3600)),
            refresh_token_expires_in=(
                int(payload["x_refresh_token_expires_in"])
                if payload.get("x_refresh_token_expires_in") is not None
                else None
            ),
            scope=str(payload.get("scope") or ACCOUNTING_SCOPE),
        )

    def _token_request(self, form: dict[str, str]) -> dict[str, Any]:
        client_id = os.environ["POLARIS_QBO_CLIENT_ID"]
        client_secret = os.environ["POLARIS_QBO_CLIENT_SECRET"]
        basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        request = Request(
            TOKEN_URL,
            data=urlencode(form).encode(),
            headers={
                "Accept": "application/json",
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise QuickBooksOAuthError(
                f"QuickBooks token exchange failed with HTTP {exc.code}"
            ) from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise QuickBooksOAuthError("QuickBooks token exchange failed") from exc

    def _create_state(self, *, organization_id: str, identity_id: str, organization_slug: str) -> str:
        timestamp = str(int(time.time()))
        nonce = secrets.token_urlsafe(24)
        body = f"{timestamp}.{nonce}"
        signature = hmac.new(
            self._state_secret().encode(), body.encode(), hashlib.sha256
        ).hexdigest()
        state = f"{body}.{signature}"
        now = datetime.now(timezone.utc)
        with SessionLocal.begin() as session:
            session.add(
                QuickBooksOAuthState(
                    state=state,
                    organization_id=organization_id,
                    identity_id=identity_id,
                    organization_slug=organization_slug,
                    created_at=now,
                    expires_at=now + timedelta(seconds=STATE_TTL_SECONDS),
                )
            )
        return state

    def _consume_state(self, state: str) -> QuickBooksOAuthContext:
        self._validate_state_signature(state)
        now = datetime.now(timezone.utc)
        with SessionLocal.begin() as session:
            record = session.get(QuickBooksOAuthState, state)
            if record is None:
                raise QuickBooksOAuthError("QuickBooks OAuth state is unknown")
            if record.consumed_at is not None:
                raise QuickBooksOAuthError("QuickBooks OAuth state has already been used")
            expires_at = record.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at <= now:
                raise QuickBooksOAuthError("QuickBooks OAuth state has expired")
            record.consumed_at = now
            return QuickBooksOAuthContext(
                organization_id=record.organization_id,
                identity_id=record.identity_id,
                organization_slug=record.organization_slug,
            )

    def _validate_state_signature(self, state: str) -> None:
        try:
            timestamp_text, nonce, signature = state.split(".", 2)
            timestamp = int(timestamp_text)
        except (ValueError, AttributeError) as exc:
            raise QuickBooksOAuthError("QuickBooks OAuth state is invalid") from exc
        body = f"{timestamp_text}.{nonce}"
        expected = hmac.new(
            self._state_secret().encode(), body.encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise QuickBooksOAuthError("QuickBooks OAuth state validation failed")
        if abs(int(time.time()) - timestamp) > STATE_TTL_SECONDS:
            raise QuickBooksOAuthError("QuickBooks OAuth state has expired")

    @staticmethod
    def _state_secret() -> str:
        secret = os.getenv("POLARIS_QBO_OAUTH_STATE_SECRET")
        if not secret or len(secret) < 32:
            raise QuickBooksOAuthError(
                "QuickBooks OAuth state signing is not configured"
            )
        return secret

    @staticmethod
    def _validate_configuration() -> None:
        missing = [
            name
            for name in (
                "POLARIS_QBO_CLIENT_ID",
                "POLARIS_QBO_CLIENT_SECRET",
                "POLARIS_QBO_REDIRECT_URI",
                "POLARIS_QBO_OAUTH_STATE_SECRET",
                "POLARIS_QBO_TOKEN_ENCRYPTION_KEY",
            )
            if not os.getenv(name)
        ]
        if missing:
            raise QuickBooksOAuthError(
                "QuickBooks OAuth is not configured. Missing environment variables: "
                + ", ".join(missing)
            )
