"""Encrypted persistence for tenant-owned Motive OAuth credentials."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from cryptography.fernet import Fernet, InvalidToken

from app.database.database import SessionLocal
from app.models.motive import MotiveCredential

logger = logging.getLogger(__name__)


class MotiveCredentialError(RuntimeError):
    """Safe Motive credential-store error that never includes OAuth secrets."""

    def __init__(self, message: str, *, failing_step: str | None = None, rollback_executed: bool | None = None) -> None:
        super().__init__(_sanitize(message))
        self.failing_step = failing_step
        self.rollback_executed = rollback_executed


@dataclass(frozen=True, slots=True)
class StoredMotiveCredential:
    organization_id: str
    organization_slug: str
    provider: str
    authentication_method: str
    access_token: str
    refresh_token: str
    expires_at: datetime
    granted_scopes: str
    token_type: str
    connection_status: str
    authorization_required: bool


class MotiveCredentialStore:
    """Store encrypted Motive OAuth tokens and expose non-secret metadata."""

    authentication_method = "oauth2"

    def __init__(self, organization_id: str) -> None:
        if not organization_id:
            raise MotiveCredentialError("Motive organization context is required")
        self.organization_id = organization_id

    def save_tokens(
        self,
        *,
        organization_slug: str,
        access_token: str,
        refresh_token: str,
        expires_at: datetime,
        granted_scopes: str,
        token_type: str = "Bearer",
        provider_company_id: str | None = None,
        provider_company_name: str | None = None,
    ) -> None:
        if not organization_slug:
            raise MotiveCredentialError("Motive organization slug is required", failing_step="ORG FOUND")
        if not access_token or not refresh_token:
            raise MotiveCredentialError("Motive OAuth tokens are required", failing_step="TOKEN RECEIVED")

        now = datetime.now(timezone.utc)
        session = SessionLocal()
        failing_step = "CREDENTIAL CREATED"
        rollback_executed = False
        try:
            credential = self._row(session, for_update=True)
            credential_created = credential is None
            _log_callback_step(
                "CREDENTIAL CREATED",
                organization_id=self.organization_id,
                organization_slug=organization_slug,
                credential_created=credential_created,
                authentication_method=self.authentication_method,
            )

            failing_step = "ENCRYPTION COMPLETE"
            encrypted_access_token = self._encrypt(access_token)
            encrypted_refresh_token = self._encrypt(refresh_token)
            _log_callback_step(
                "ENCRYPTION COMPLETE",
                organization_id=self.organization_id,
                token_received=True,
                access_token_encrypted=True,
                refresh_token_encrypted=True,
            )

            failing_step = "DB COMMIT SUCCESS"
            if credential is None:
                session.add(
                    MotiveCredential(
                        organization_id=self.organization_id,
                        organization_slug=organization_slug,
                        provider="motive",
                        authentication_method=self.authentication_method,
                        encrypted_access_token=encrypted_access_token,
                        encrypted_refresh_token=encrypted_refresh_token,
                        expires_at=expires_at,
                        granted_scopes=granted_scopes,
                        token_type=token_type or "Bearer",
                        provider_company_id=provider_company_id,
                        provider_company_name=provider_company_name,
                        connection_status="configured_unverified",
                        authorization_required=False,
                        created_at=now,
                        updated_at=now,
                    )
                )
            else:
                credential.organization_slug = organization_slug
                credential.encrypted_access_token = encrypted_access_token
                credential.encrypted_refresh_token = encrypted_refresh_token
                credential.expires_at = expires_at
                credential.granted_scopes = granted_scopes
                credential.token_type = token_type or "Bearer"
                credential.provider_company_id = provider_company_id or credential.provider_company_id
                credential.provider_company_name = provider_company_name or credential.provider_company_name
                credential.connection_status = "configured_unverified"
                credential.authorization_required = False
                credential.last_error_code = None
                credential.last_error_message_sanitized = None
                credential.disconnected_at = None
                credential.updated_at = now

            session.commit()
            _log_callback_step(
                "DB COMMIT SUCCESS",
                organization_id=self.organization_id,
                organization_slug=organization_slug,
                credential_created=credential_created,
                connection_status="configured_unverified",
                rollback_executed=False,
            )
        except Exception as exc:
            try:
                session.rollback()
                rollback_executed = True
            except Exception:
                rollback_executed = False
            _log_callback_exception(
                exception_class=exc.__class__.__name__,
                failing_step=failing_step,
                organization_id=self.organization_id,
                rollback_executed=rollback_executed,
            )
            if isinstance(exc, MotiveCredentialError):
                exc.failing_step = exc.failing_step or failing_step
                exc.rollback_executed = rollback_executed
                raise
            raise MotiveCredentialError(
                f"Motive credential persistence failed at {failing_step}",
                failing_step=failing_step,
                rollback_executed=rollback_executed,
            ) from exc
        finally:
            session.close()

    def load_tokens(self) -> StoredMotiveCredential:
        with SessionLocal() as session:
            credential = self._row(session)
            if credential is None or credential.disconnected_at is not None:
                raise MotiveCredentialError("Motive OAuth credential is not configured")
            return StoredMotiveCredential(
                organization_id=credential.organization_id,
                organization_slug=credential.organization_slug,
                provider=credential.provider,
                authentication_method=credential.authentication_method,
                access_token=self._decrypt(credential.encrypted_access_token),
                refresh_token=self._decrypt(credential.encrypted_refresh_token),
                expires_at=credential.expires_at,
                granted_scopes=credential.granted_scopes,
                token_type=credential.token_type,
                connection_status=credential.connection_status,
                authorization_required=credential.authorization_required,
            )

    def rotate_tokens(
        self,
        *,
        access_token: str,
        refresh_token: str | None,
        expires_at: datetime,
        granted_scopes: str | None = None,
        token_type: str | None = None,
    ) -> None:
        if not access_token:
            raise MotiveCredentialError("Motive OAuth access token is required")
        with SessionLocal.begin() as session:
            credential = self._row(session, for_update=True)
            if credential is None or credential.disconnected_at is not None:
                raise MotiveCredentialError("Motive OAuth credential is not configured")
            credential.encrypted_access_token = self._encrypt(access_token)
            if refresh_token:
                credential.encrypted_refresh_token = self._encrypt(refresh_token)
            credential.expires_at = expires_at
            if granted_scopes:
                credential.granted_scopes = granted_scopes
            if token_type:
                credential.token_type = token_type
            credential.authorization_required = False
            credential.connection_status = "configured_unverified"
            credential.last_error_code = None
            credential.last_error_message_sanitized = None
            credential.updated_at = datetime.now(timezone.utc)

    def metadata(self) -> dict[str, object]:
        with SessionLocal() as session:
            credential = self._row(session)
            if credential is None or credential.disconnected_at is not None:
                return {
                    "provider": "motive",
                    "authentication_method": self.authentication_method,
                    "authorized": False,
                    "token_present": False,
                    "connection_status": "not_configured",
                    "authorization_required": True,
                    "secrets_exposed": False,
                }
            return {
                "organization_id": credential.organization_id,
                "organization_slug": credential.organization_slug,
                "provider": credential.provider,
                "authentication_method": credential.authentication_method,
                "authorized": bool(credential.encrypted_refresh_token) and not credential.authorization_required,
                "token_present": bool(credential.encrypted_refresh_token),
                "expires_at": credential.expires_at.isoformat() if credential.expires_at else None,
                "granted_scopes": credential.granted_scopes,
                "token_type": credential.token_type,
                "provider_company_id": credential.provider_company_id,
                "provider_company_name": credential.provider_company_name,
                "connection_status": credential.connection_status,
                "authorization_required": credential.authorization_required,
                "last_verified_at": credential.last_verified_at.isoformat() if credential.last_verified_at else None,
                "last_successful_sync_at": credential.last_successful_sync_at.isoformat() if credential.last_successful_sync_at else None,
                "last_error_code": credential.last_error_code,
                "last_error_message_sanitized": credential.last_error_message_sanitized,
                "created_at": credential.created_at.isoformat() if credential.created_at else None,
                "updated_at": credential.updated_at.isoformat() if credential.updated_at else None,
                "secrets_exposed": False,
            }

    def record_verification_success(
        self,
        *,
        verified_at: datetime | None = None,
        provider_company_id: str | None = None,
        provider_company_name: str | None = None,
    ) -> None:
        values: dict[str, object] = {
            "connection_status": "connected",
            "authorization_required": False,
            "last_verified_at": verified_at or datetime.now(timezone.utc),
            "last_error_code": None,
            "last_error_message_sanitized": None,
        }
        if provider_company_id:
            values["provider_company_id"] = provider_company_id
        if provider_company_name:
            values["provider_company_name"] = provider_company_name
        self.update_metadata(**values)

    def record_failure(
        self,
        *,
        status: str,
        error_code: str,
        error_message_sanitized: str,
        authorization_required: bool = False,
    ) -> None:
        self.update_metadata(
            connection_status=status,
            authorization_required=authorization_required,
            last_error_code=error_code,
            last_error_message_sanitized=_sanitize(error_message_sanitized),
        )

    def update_metadata(self, **values: object) -> None:
        with SessionLocal.begin() as session:
            credential = self._row(session, for_update=True)
            if credential is None:
                return
            for key, value in values.items():
                if hasattr(credential, key):
                    setattr(credential, key, value)
            credential.updated_at = datetime.now(timezone.utc)

    def delete(self) -> None:
        with SessionLocal.begin() as session:
            credential = self._row(session, for_update=True)
            if credential is not None:
                credential.disconnected_at = datetime.now(timezone.utc)
                credential.authorization_required = True
                credential.connection_status = "not_configured"
                credential.updated_at = datetime.now(timezone.utc)

    @staticmethod
    def _fernet() -> Fernet:
        from os import getenv

        key = getenv("POLARIS_MOTIVE_TOKEN_ENCRYPTION_KEY") or getenv("POLARIS_QBO_TOKEN_ENCRYPTION_KEY")
        if not key:
            raise MotiveCredentialError(
                "Motive token encryption is not configured. Missing POLARIS_MOTIVE_TOKEN_ENCRYPTION_KEY"
            )
        try:
            return Fernet(key.encode("utf-8"))
        except (TypeError, ValueError) as exc:
            raise MotiveCredentialError("POLARIS_MOTIVE_TOKEN_ENCRYPTION_KEY is not a valid Fernet key") from exc

    @classmethod
    def _encrypt(cls, value: str) -> str:
        return cls._fernet().encrypt(value.encode("utf-8")).decode("utf-8")

    @classmethod
    def _decrypt(cls, encrypted_value: str) -> str:
        try:
            return cls._fernet().decrypt(encrypted_value.encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            raise MotiveCredentialError("Motive credential encryption key is invalid") from exc

    def _row(self, session, *, for_update: bool = False) -> MotiveCredential | None:
        query = session.query(MotiveCredential).filter_by(
            organization_id=self.organization_id,
            authentication_method=self.authentication_method,
        )
        if for_update:
            query = query.with_for_update()
        return query.one_or_none()


def _log_callback_step(step: str, **fields: object) -> None:
    logger.info("MOTIVE OAUTH CALLBACK %s", step, extra={"motive_oauth_step": step, **fields})


def _log_callback_exception(*, exception_class: str, failing_step: str, organization_id: str, rollback_executed: bool) -> None:
    logger.info(
        "MOTIVE OAUTH CALLBACK EXCEPTION",
        extra={
            "motive_oauth_step": "EXCEPTION",
            "exception_class": exception_class,
            "failing_step": failing_step,
            "organization_id": organization_id,
            "rollback_executed": rollback_executed,
        },
    )


def _sanitize(message: str) -> str:
    sanitized = " ".join(str(message).split())
    for marker in ("access_token", "refresh_token", "authorization", "bearer", "client_secret", "code", "token", "secret"):
        sanitized = sanitized.replace(marker, "credential")
        sanitized = sanitized.replace(marker.upper(), "CREDENTIAL")
    return sanitized[:500]
