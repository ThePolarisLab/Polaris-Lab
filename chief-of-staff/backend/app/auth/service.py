"""Production authentication bootstrap, password login, and session rotation."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
import secrets
from typing import Any

import bcrypt
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.models import (
    ProductionAuthBootstrapState,
    ProductionAuthSession,
    ProductionLoginAttempt,
    ProductionPasswordCredential,
)
from app.events import ConnectorEvent, EventActor, EventSource, EventSubject, event_bus
from app.identity.models import Identity, IdentityStatus, MembershipStatus, OrganizationMembership
from app.organizations.models import Organization, OrganizationStatus
from app.security.models import AuthenticatedPrincipal, AuthenticationResult, Permission, ROLE_PERMISSIONS
from app.security.service import AuthenticationError, AuthorizationError

PRODUCTION_ENVIRONMENTS = {"production", "prod", "staging"}
BOOTSTRAP_ID = "first-admin"
BOOTSTRAP_ORGANIZATION_ID = "org-mor-logistics"
BOOTSTRAP_ORGANIZATION_SLUG = "mor-logistics"
BOOTSTRAP_ORGANIZATION_DISPLAY_NAME = "MOR Logistics"
BOOTSTRAP_ORGANIZATION_LEGAL_NAME = "MOR LOGISTICS MANITOBA LIMITED"
BOOTSTRAP_IDENTITY_ID = "mor-admin"
BOOTSTRAP_ROLE = "owner"
MIN_SECRET_LENGTH = 32
MIN_PASSWORD_LENGTH = 12
MAX_FAILED_ATTEMPTS = 5
RATE_LIMIT_WINDOW_SECONDS = 15 * 60


class BootstrapUnavailableError(PermissionError):
    """Raised when the one-time bootstrap path is unavailable."""


class BootstrapConfigurationError(RuntimeError):
    """Raised when required bootstrap configuration is missing or weak."""


class RateLimitError(PermissionError):
    """Raised when login attempts are rate-limited."""


@dataclass(frozen=True)
class SessionTokens:
    access_token: str
    refresh_token: str
    organization_id: str
    expires_in: int
    refresh_expires_in: int


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _json_default(value: Any) -> str:
    raise TypeError(f"unsupported value: {type(value)!r}")


def _access_token_secret() -> bytes:
    configured = os.getenv("POLARIS_SESSION_SECRET", "").strip()
    environment = os.getenv("POLARIS_ENV", "development").strip().lower()
    if environment in PRODUCTION_ENVIRONMENTS:
        if len(configured) < MIN_SECRET_LENGTH:
            raise AuthenticationError("session secret is not configured")
        return configured.encode()
    return (configured or "test-session-secret-with-enough-length").encode()


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise BootstrapConfigurationError(f"{name} must be an integer") from exc


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _normalize_email(value: str) -> str:
    return value.strip().lower()


def hash_password(password: str) -> str:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError("password must be at least 12 characters")
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False


def _issue_access_token(identity_id: str, organization_id: str, session_id: str, ttl_seconds: int) -> str:
    payload: dict[str, Any] = {
        "typ": "access",
        "sub": identity_id,
        "org": organization_id,
        "sid": session_id,
        "iat": int(_now().timestamp()),
        "exp": int((_now() + timedelta(seconds=ttl_seconds)).timestamp()),
    }
    encoded = _encode(json.dumps(payload, separators=(",", ":"), default=_json_default).encode())
    signature = _encode(hmac.new(_access_token_secret(), encoded.encode(), hashlib.sha256).digest())
    return f"{encoded}.{signature}"


def _validate_access_token(token: str) -> dict[str, Any]:
    try:
        encoded, signature = token.split(".", 1)
        expected = _encode(hmac.new(_access_token_secret(), encoded.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise AuthenticationError("invalid credential signature")
        payload = json.loads(_decode(encoded))
        if payload.get("typ") != "access":
            raise AuthenticationError("invalid credential")
        if int(payload["exp"]) <= int(_now().timestamp()):
            raise AuthenticationError("credential expired")
        return payload
    except AuthenticationError:
        raise
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise AuthenticationError("invalid credential") from exc


class ProductionSessionProvider:
    """AuthenticationProvider-compatible access-token validator."""

    name = "production-session"

    def __init__(self, session: Session, organization_id: str) -> None:
        self._session = session
        self._organization_id = organization_id

    def validate(self, credential: str) -> AuthenticationResult:
        principal = ProductionAuthService(self._session).authenticate_access_token(credential, self._organization_id)
        return AuthenticationResult(
            provider=self.name,
            subject=principal.identity_id,
            claims={"organization_id": principal.organization_id, "session_id": principal.claims.get("session_id")},
        )


class ProductionAuthService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def bootstrap_available(self) -> bool:
        return self._session.get(ProductionAuthBootstrapState, BOOTSTRAP_ID) is None

    def complete_bootstrap(self, *, bootstrap_secret: str, password: str, ip_address: str | None = None) -> dict[str, str]:
        configured_secret = os.getenv("POLARIS_BOOTSTRAP_SECRET", "").strip()
        admin_email = _normalize_email(os.getenv("POLARIS_BOOTSTRAP_ADMIN_EMAIL", ""))
        if len(configured_secret) < MIN_SECRET_LENGTH or not admin_email:
            self._audit("identity.bootstrap.rejected.v1", BOOTSTRAP_ORGANIZATION_ID, BOOTSTRAP_IDENTITY_ID, {"reason": "configuration"})
            raise BootstrapConfigurationError("bootstrap configuration is missing")
        if not hmac.compare_digest(bootstrap_secret, configured_secret):
            self._audit("identity.bootstrap.rejected.v1", BOOTSTRAP_ORGANIZATION_ID, BOOTSTRAP_IDENTITY_ID, {"reason": "invalid_secret"})
            raise BootstrapUnavailableError("bootstrap is not available")
        if not self.bootstrap_available():
            raise BootstrapUnavailableError("bootstrap has already been completed")

        password_hash = hash_password(password)
        organization = self._session.get(Organization, BOOTSTRAP_ORGANIZATION_ID)
        if organization is not None:
            if organization.slug != BOOTSTRAP_ORGANIZATION_SLUG or organization.legal_name != BOOTSTRAP_ORGANIZATION_LEGAL_NAME:
                raise BootstrapUnavailableError("existing organization does not match bootstrap target")
        else:
            organization = Organization(
                id=BOOTSTRAP_ORGANIZATION_ID,
                slug=BOOTSTRAP_ORGANIZATION_SLUG,
                display_name=BOOTSTRAP_ORGANIZATION_DISPLAY_NAME,
                legal_name=BOOTSTRAP_ORGANIZATION_LEGAL_NAME,
                status=OrganizationStatus.ACTIVE.value,
            )
            self._session.add(organization)

        identity = self._session.get(Identity, BOOTSTRAP_IDENTITY_ID)
        if identity is not None:
            if _normalize_email(identity.email) != admin_email:
                raise BootstrapUnavailableError("existing identity does not match bootstrap email")
            identity.status = IdentityStatus.ACTIVE.value
            identity.display_name = identity.display_name or "MOR Admin"
        else:
            identity = Identity(
                id=BOOTSTRAP_IDENTITY_ID,
                email=admin_email,
                display_name="MOR Admin",
                status=IdentityStatus.ACTIVE.value,
            )
            self._session.add(identity)

        membership = (
            self._session.query(OrganizationMembership)
            .filter(
                OrganizationMembership.organization_id == BOOTSTRAP_ORGANIZATION_ID,
                OrganizationMembership.identity_id == BOOTSTRAP_IDENTITY_ID,
            )
            .first()
        )
        if membership is None:
            membership = OrganizationMembership(
                organization_id=BOOTSTRAP_ORGANIZATION_ID,
                identity_id=BOOTSTRAP_IDENTITY_ID,
                role=BOOTSTRAP_ROLE,
                status=MembershipStatus.ACTIVE.value,
            )
            self._session.add(membership)
        else:
            membership.role = BOOTSTRAP_ROLE
            membership.status = MembershipStatus.ACTIVE.value

        credential = self._session.get(ProductionPasswordCredential, BOOTSTRAP_IDENTITY_ID)
        if credential is None:
            credential = ProductionPasswordCredential(identity_id=BOOTSTRAP_IDENTITY_ID, password_hash=password_hash)
            self._session.add(credential)
        else:
            credential.password_hash = password_hash
            credential.algorithm = "bcrypt"
            credential.updated_at = _now()

        self._session.add(
            ProductionAuthBootstrapState(
                id=BOOTSTRAP_ID,
                organization_id=BOOTSTRAP_ORGANIZATION_ID,
                identity_id=BOOTSTRAP_IDENTITY_ID,
                completed=True,
            )
        )
        self._session.flush()
        self._audit("identity.bootstrap.completed.v1", BOOTSTRAP_ORGANIZATION_ID, BOOTSTRAP_IDENTITY_ID, {"ip_address": bool(ip_address)})
        return {"organization_id": BOOTSTRAP_ORGANIZATION_ID, "identity_id": BOOTSTRAP_IDENTITY_ID}

    def login(self, *, email: str, password: str, ip_address: str | None = None, user_agent: str | None = None) -> SessionTokens:
        normalized = _normalize_email(email)
        if self._rate_limited(normalized, ip_address):
            self._record_login_attempt(normalized, ip_address, False, "rate_limited")
            raise RateLimitError("too many failed login attempts")

        identity = self._session.query(Identity).filter(func.lower(Identity.email) == normalized).first()
        credential = self._session.get(ProductionPasswordCredential, identity.id) if identity is not None else None
        if identity is None or credential is None or not verify_password(password, credential.password_hash):
            self._record_login_attempt(normalized, ip_address, False, "invalid_credentials")
            raise AuthenticationError("invalid email or password")
        if identity.status != IdentityStatus.ACTIVE.value:
            self._record_login_attempt(normalized, ip_address, False, "inactive_identity")
            raise AuthenticationError("identity is not active")

        membership = (
            self._session.query(OrganizationMembership)
            .filter(
                OrganizationMembership.identity_id == identity.id,
                OrganizationMembership.status == MembershipStatus.ACTIVE.value,
            )
            .order_by(OrganizationMembership.organization_id.asc())
            .first()
        )
        if membership is None:
            self._record_login_attempt(normalized, ip_address, False, "inactive_membership")
            raise AuthorizationError("active organization membership required")

        tokens = self._create_session(identity.id, membership.organization_id, ip_address, user_agent)
        self._record_login_attempt(normalized, ip_address, True, None)
        self._audit("identity.authentication.succeeded.v1", membership.organization_id, identity.id, {"provider": "password"})
        return tokens

    def refresh(self, *, refresh_token: str, ip_address: str | None = None, user_agent: str | None = None) -> SessionTokens:
        token_hash = _token_hash(refresh_token)
        existing = self._session.query(ProductionAuthSession).filter(ProductionAuthSession.refresh_token_hash == token_hash).first()
        if existing is None or existing.revoked_at is not None:
            raise AuthenticationError("invalid refresh token")
        if _as_aware(existing.refresh_expires_at) <= _now():
            existing.revoked_at = _now()
            existing.revoke_reason = "expired"
            raise AuthenticationError("refresh token expired")

        existing.revoked_at = _now()
        existing.revoke_reason = "rotated"
        tokens = self._create_session(
            existing.identity_id,
            existing.organization_id,
            ip_address,
            user_agent,
            rotated_from_session_id=existing.id,
        )
        self._audit("identity.session.refreshed.v1", existing.organization_id, existing.identity_id, {"session_rotated": True})
        return tokens

    def logout_access_token(self, access_token: str) -> None:
        payload = _validate_access_token(access_token)
        session_id = str(payload.get("sid", ""))
        auth_session = self._session.get(ProductionAuthSession, session_id)
        if auth_session is not None and auth_session.revoked_at is None:
            auth_session.revoked_at = _now()
            auth_session.revoke_reason = "logout"
            self._audit("identity.session.revoked.v1", auth_session.organization_id, auth_session.identity_id, {"reason": "logout"})

    def authenticate_access_token(self, access_token: str, organization_id: str) -> AuthenticatedPrincipal:
        payload = _validate_access_token(access_token)
        if str(payload.get("org", "")) != organization_id:
            raise AuthorizationError("organization access denied")
        auth_session = self._session.get(ProductionAuthSession, str(payload.get("sid", "")))
        if auth_session is None or auth_session.revoked_at is not None:
            raise AuthenticationError("session is not active")
        if _as_aware(auth_session.access_expires_at) <= _now() or _as_aware(auth_session.refresh_expires_at) <= _now():
            raise AuthenticationError("credential expired")
        if auth_session.identity_id != str(payload.get("sub", "")) or auth_session.organization_id != organization_id:
            raise AuthorizationError("organization access denied")

        identity = self._session.get(Identity, auth_session.identity_id)
        if identity is None or identity.status != IdentityStatus.ACTIVE.value:
            raise AuthenticationError("identity is not active")
        membership = (
            self._session.query(OrganizationMembership)
            .filter(
                OrganizationMembership.identity_id == identity.id,
                OrganizationMembership.organization_id == organization_id,
            )
            .first()
        )
        if membership is None or membership.status != MembershipStatus.ACTIVE.value:
            raise AuthorizationError("active organization membership required")
        auth_session.last_used_at = _now()
        permissions = ROLE_PERMISSIONS.get(membership.role, frozenset())
        return AuthenticatedPrincipal(
            identity_id=identity.id,
            organization_id=organization_id,
            membership_id=str(membership.id),
            role=membership.role,
            permissions=permissions,
            provider="production-session",
            subject=identity.id,
            claims={"session_id": auth_session.id},
        )

    def _create_session(
        self,
        identity_id: str,
        organization_id: str,
        ip_address: str | None,
        user_agent: str | None,
        *,
        rotated_from_session_id: str | None = None,
    ) -> SessionTokens:
        access_ttl = _int_env("POLARIS_ACCESS_TOKEN_TTL_SECONDS", 900)
        refresh_ttl = _int_env("POLARIS_REFRESH_TOKEN_TTL_SECONDS", 60 * 60 * 24 * 14)
        refresh_token = secrets.token_urlsafe(48)
        auth_session = ProductionAuthSession(
            identity_id=identity_id,
            organization_id=organization_id,
            refresh_token_hash=_token_hash(refresh_token),
            rotated_from_session_id=rotated_from_session_id,
            user_agent=user_agent[:500] if user_agent else None,
            ip_address=ip_address,
            access_expires_at=_now() + timedelta(seconds=access_ttl),
            refresh_expires_at=_now() + timedelta(seconds=refresh_ttl),
        )
        self._session.add(auth_session)
        self._session.flush()
        access_token = _issue_access_token(identity_id, organization_id, auth_session.id, access_ttl)
        return SessionTokens(
            access_token=access_token,
            refresh_token=refresh_token,
            organization_id=organization_id,
            expires_in=access_ttl,
            refresh_expires_in=refresh_ttl,
        )

    def _rate_limited(self, email: str, ip_address: str | None) -> bool:
        since = _now() - timedelta(seconds=RATE_LIMIT_WINDOW_SECONDS)
        query = self._session.query(ProductionLoginAttempt).filter(
            ProductionLoginAttempt.email == email,
            ProductionLoginAttempt.succeeded.is_(False),
            ProductionLoginAttempt.created_at >= since,
        )
        if ip_address:
            query = query.filter(ProductionLoginAttempt.ip_address == ip_address)
        return int(query.count()) >= MAX_FAILED_ATTEMPTS

    def _record_login_attempt(self, email: str, ip_address: str | None, succeeded: bool, failure_reason: str | None) -> None:
        self._session.add(
            ProductionLoginAttempt(
                email=email,
                ip_address=ip_address,
                succeeded=succeeded,
                failure_reason=failure_reason,
            )
        )
        event_type = "identity.authentication.succeeded.v1" if succeeded else "identity.authentication.failed.v1"
        self._audit(event_type, "unknown", "unknown", {"reason": failure_reason or "success"})

    @staticmethod
    def _audit(event_type: str, organization_id: str, identity_id: str, payload: dict[str, Any]) -> None:
        event_bus.publish(
            ConnectorEvent(
                event_type=event_type,
                organization_id=organization_id,
                tenant_id=organization_id,
                source=EventSource(service="production-auth"),
                actor=EventActor(actor_type="identity", actor_id=identity_id),
                subject=EventSubject(subject_type="identity", subject_id=identity_id),
                idempotency_key=f"{event_type}:{organization_id}:{identity_id}:{secrets.token_hex(8)}",
                payload=payload,
            )
        )


def is_managed_environment() -> bool:
    return os.getenv("POLARIS_ENV", "development").strip().lower() in PRODUCTION_ENVIRONMENTS
