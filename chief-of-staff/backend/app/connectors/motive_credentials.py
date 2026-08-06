"""Encrypted persistence for tenant-owned Motive API-key credentials."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from cryptography.fernet import Fernet, InvalidToken

from app.database.database import SessionLocal
from app.models.motive import MotiveCredential


class MotiveCredentialError(RuntimeError):
    """Safe Motive credential-store error that never includes API-key values."""


@dataclass(frozen=True, slots=True)
class StoredMotiveCredential:
    organization_id: str
    organization_slug: str
    provider: str
    authentication_method: str
    environment_mode: str
    api_key: str
    connection_status: str
    authorization_required: bool


class MotiveCredentialStore:
    """Store encrypted Motive API keys and expose non-secret metadata."""

    def __init__(self, organization_id: str) -> None:
        if not organization_id:
            raise MotiveCredentialError("Motive organization context is required")
        self.organization_id = organization_id

    def save_api_key(self, *, organization_slug: str, api_key: str, environment_mode: str = "test") -> None:
        if not organization_slug:
            raise MotiveCredentialError("Motive organization slug is required")
        if not api_key:
            raise MotiveCredentialError("Motive API key is required")
        encrypted = self._encrypt(api_key)
        now = datetime.now(timezone.utc)
        with SessionLocal.begin() as session:
            credential = self._row(session, environment_mode=environment_mode)
            if credential is None:
                session.add(
                    MotiveCredential(
                        organization_id=self.organization_id,
                        organization_slug=organization_slug,
                        provider="motive",
                        authentication_method="api_key",
                        environment_mode=environment_mode,
                        encrypted_api_key=encrypted,
                        key_present=True,
                        connection_status="configured_unverified",
                        authorization_required=False,
                        created_at=now,
                        updated_at=now,
                    )
                )
                return
            credential.organization_slug = organization_slug
            credential.encrypted_api_key = encrypted
            credential.key_present = True
            credential.connection_status = "configured_unverified"
            credential.authorization_required = False
            credential.last_error_code = None
            credential.last_error_message_sanitized = None
            credential.disconnected_at = None
            credential.updated_at = now

    def load_api_key(self, *, environment_mode: str | None = None) -> StoredMotiveCredential:
        with SessionLocal() as session:
            credential = self._row(session, environment_mode=environment_mode)
            if credential is None or credential.disconnected_at is not None:
                raise MotiveCredentialError("Motive API-key credential is not configured")
            return StoredMotiveCredential(
                organization_id=credential.organization_id,
                organization_slug=credential.organization_slug,
                provider=credential.provider,
                authentication_method=credential.authentication_method,
                environment_mode=credential.environment_mode,
                api_key=self._decrypt(credential.encrypted_api_key),
                connection_status=credential.connection_status,
                authorization_required=credential.authorization_required,
            )

    def metadata(self, *, environment_mode: str | None = None) -> dict[str, object]:
        with SessionLocal() as session:
            credential = self._row(session, environment_mode=environment_mode)
            if credential is None or credential.disconnected_at is not None:
                return {
                    "provider": "motive",
                    "authentication_method": "api_key",
                    "authorized": False,
                    "key_present": False,
                    "connection_status": "not_configured",
                    "authorization_required": True,
                    "secrets_exposed": False,
                }
            return {
                "organization_id": credential.organization_id,
                "organization_slug": credential.organization_slug,
                "provider": credential.provider,
                "authentication_method": credential.authentication_method,
                "environment_mode": credential.environment_mode,
                "authorized": credential.key_present and not credential.authorization_required,
                "key_present": credential.key_present,
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

    def record_verification_success(self, *, environment_mode: str, verified_at: datetime | None = None) -> None:
        self.update_metadata(
            environment_mode=environment_mode,
            connection_status="connected",
            authorization_required=False,
            last_verified_at=verified_at or datetime.now(timezone.utc),
            last_error_code=None,
            last_error_message_sanitized=None,
        )

    def record_verification_failure(
        self,
        *,
        environment_mode: str,
        status: str,
        error_code: str,
        error_message_sanitized: str,
        authorization_required: bool = False,
    ) -> None:
        self.update_metadata(
            environment_mode=environment_mode,
            connection_status=status,
            authorization_required=authorization_required,
            last_error_code=error_code,
            last_error_message_sanitized=_sanitize(error_message_sanitized),
        )

    def update_metadata(self, *, environment_mode: str | None = None, **values: object) -> None:
        with SessionLocal.begin() as session:
            credential = self._row(session, environment_mode=environment_mode)
            if credential is None:
                return
            for key, value in values.items():
                if hasattr(credential, key):
                    setattr(credential, key, value)
            credential.updated_at = datetime.now(timezone.utc)

    def delete(self, *, environment_mode: str | None = None) -> None:
        with SessionLocal.begin() as session:
            credential = self._row(session, environment_mode=environment_mode)
            if credential is not None:
                credential.disconnected_at = datetime.now(timezone.utc)
                credential.key_present = False
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
    def _encrypt(cls, api_key: str) -> str:
        return cls._fernet().encrypt(api_key.encode("utf-8")).decode("utf-8")

    @classmethod
    def _decrypt(cls, encrypted_api_key: str) -> str:
        try:
            return cls._fernet().decrypt(encrypted_api_key.encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            raise MotiveCredentialError("Motive credential encryption key is invalid") from exc

    def _row(self, session, *, environment_mode: str | None = None, for_update: bool = False) -> MotiveCredential | None:
        query = session.query(MotiveCredential).filter_by(
            organization_id=self.organization_id,
            authentication_method="api_key",
        )
        if environment_mode:
            query = query.filter_by(environment_mode=environment_mode)
        query = query.order_by(MotiveCredential.updated_at.desc())
        if for_update:
            query = query.with_for_update()
        return query.first()


def _sanitize(message: str) -> str:
    sanitized = " ".join(str(message).split())
    for marker in ("api_key", "apikey", "x-api-key", "authorization", "token", "secret"):
        sanitized = sanitized.replace(marker, "credential")
        sanitized = sanitized.replace(marker.upper(), "CREDENTIAL")
    return sanitized[:500]
