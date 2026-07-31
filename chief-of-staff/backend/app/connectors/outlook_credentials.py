"""Encrypted persistence for tenant-owned Microsoft Outlook OAuth credentials."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base, SessionLocal


class OutlookCredentialError(RuntimeError):
    """Safe credential-store error that never includes secret values."""


@dataclass(frozen=True)
class StoredOutlookCredential:
    organization_id: str
    organization_slug: str
    microsoft_tenant_id: str
    mailbox_user_id: str
    mailbox_address: str
    refresh_token: str
    scopes: str
    connector_health_status: str
    reauthorization_required: bool
    last_error_summary: str | None
    last_successful_sync_at: datetime | None
    last_refresh_at: datetime | None
    last_refresh_status: str | None
    connected_at: datetime
    updated_at: datetime
    disconnected_at: datetime | None


class OutlookOAuthCredential(Base):
    """Microsoft Outlook OAuth credentials for one Polaris organization."""

    __tablename__ = "outlook_oauth_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[str] = mapped_column(String, ForeignKey("organizations.id"), nullable=False, unique=True, index=True)
    organization_slug: Mapped[str] = mapped_column(String, nullable=False, index=True)
    microsoft_tenant_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    mailbox_user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    mailbox_address: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    encrypted_refresh_token: Mapped[str] = mapped_column(Text, nullable=False)
    scopes: Mapped[str] = mapped_column(Text, nullable=False)
    connector_health_status: Mapped[str] = mapped_column(String(60), nullable=False, default="connected_unverified")
    reauthorization_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_successful_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_refresh_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_refresh_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    disconnected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    organization = relationship("Organization")


class OutlookOAuthState(Base):
    """Single-use Microsoft OAuth state bound to a Polaris principal."""

    __tablename__ = "outlook_oauth_states"
    state: Mapped[str] = mapped_column(String(255), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String, ForeignKey("organizations.id"), nullable=False, index=True)
    identity_id: Mapped[str] = mapped_column(String, ForeignKey("identities.id"), nullable=False, index=True)
    nonce: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    organization = relationship("Organization")
    identity = relationship("Identity")


class OutlookCredentialStore:
    """Read, rotate, and delete encrypted Microsoft refresh tokens."""

    def __init__(self, organization_id: str) -> None:
        if not organization_id:
            raise OutlookCredentialError("Outlook organization context is required")
        self.organization_id = organization_id

    def save(
        self,
        *,
        organization_slug: str,
        microsoft_tenant_id: str,
        mailbox_user_id: str,
        mailbox_address: str,
        refresh_token: str,
        scopes: str,
    ) -> None:
        if not all([organization_slug, microsoft_tenant_id, mailbox_user_id, mailbox_address, refresh_token, scopes]):
            raise OutlookCredentialError("Outlook OAuth credentials are incomplete")
        encrypted = self._encrypt(refresh_token)
        now = datetime.now(timezone.utc)
        with SessionLocal.begin() as session:
            credential = self._row(session)
            if credential is None:
                credential = OutlookOAuthCredential(
                    organization_id=self.organization_id,
                    organization_slug=organization_slug,
                    microsoft_tenant_id=microsoft_tenant_id,
                    mailbox_user_id=mailbox_user_id,
                    mailbox_address=mailbox_address.lower(),
                    encrypted_refresh_token=encrypted,
                    scopes=scopes,
                    connector_health_status="connected_unverified",
                    reauthorization_required=False,
                    connected_at=now,
                    updated_at=now,
                )
                session.add(credential)
                return
            credential.organization_slug = organization_slug
            credential.microsoft_tenant_id = microsoft_tenant_id
            credential.mailbox_user_id = mailbox_user_id
            credential.mailbox_address = mailbox_address.lower()
            credential.encrypted_refresh_token = encrypted
            credential.scopes = scopes
            credential.connector_health_status = "connected_unverified"
            credential.reauthorization_required = False
            credential.last_error_summary = None
            credential.disconnected_at = None
            credential.updated_at = now

    def load_credential(self) -> StoredOutlookCredential:
        with SessionLocal() as session:
            credential = self._row(session)
            if credential is None or credential.disconnected_at is not None:
                raise OutlookCredentialError("Outlook has not been authorized through the Polaris OAuth flow")
            refresh_token = self._decrypt(credential.encrypted_refresh_token)
            return StoredOutlookCredential(
                organization_id=credential.organization_id,
                organization_slug=credential.organization_slug,
                microsoft_tenant_id=credential.microsoft_tenant_id,
                mailbox_user_id=credential.mailbox_user_id,
                mailbox_address=credential.mailbox_address,
                refresh_token=refresh_token,
                scopes=credential.scopes,
                connector_health_status=credential.connector_health_status,
                reauthorization_required=credential.reauthorization_required,
                last_error_summary=credential.last_error_summary,
                last_successful_sync_at=credential.last_successful_sync_at,
                last_refresh_at=credential.last_refresh_at,
                last_refresh_status=credential.last_refresh_status,
                connected_at=credential.connected_at,
                updated_at=credential.updated_at,
                disconnected_at=credential.disconnected_at,
            )

    def rotate_refresh_token(self, *, refresh_token: str, scopes: str | None = None) -> None:
        if not refresh_token:
            raise OutlookCredentialError("Outlook refresh token rotation returned incomplete credentials")
        encrypted = self._encrypt(refresh_token)
        now = datetime.now(timezone.utc)
        with SessionLocal.begin() as session:
            credential = self._row(session, for_update=True)
            if credential is None:
                raise OutlookCredentialError("Outlook credential disappeared during token rotation")
            credential.encrypted_refresh_token = encrypted
            if scopes:
                credential.scopes = scopes
            credential.last_refresh_at = now
            credential.last_refresh_status = "success"
            credential.reauthorization_required = False
            credential.connector_health_status = "healthy"
            credential.updated_at = now

    def record_refresh_failure(self, message: str, *, reauthorization_required: bool = False) -> None:
        self.update_metadata(
            connector_health_status="reauthorization_required" if reauthorization_required else "degraded",
            reauthorization_required=reauthorization_required,
            last_refresh_status="failed",
            last_error_summary=message,
        )

    def record_sync_success(self) -> None:
        self.update_metadata(
            connector_health_status="healthy",
            reauthorization_required=False,
            last_successful_sync_at=datetime.now(timezone.utc),
            last_error_summary=None,
        )

    def record_sync_failure(self, message: str, *, status: str = "synchronization_failed") -> None:
        self.update_metadata(connector_health_status=status, last_error_summary=message)

    def update_metadata(self, **values: object) -> None:
        with SessionLocal.begin() as session:
            credential = self._row(session)
            if credential is None:
                return
            for key, value in values.items():
                if hasattr(credential, key):
                    setattr(credential, key, value)
            credential.updated_at = datetime.now(timezone.utc)

    def metadata(self) -> dict[str, object]:
        with SessionLocal() as session:
            credential = self._row(session)
            if credential is None or credential.disconnected_at is not None:
                return {
                    "authorized": False,
                    "connector_health_status": "authorization_required",
                    "reauthorization_required": True,
                }
            return {
                "authorized": True,
                "organization_id": credential.organization_id,
                "mailbox_address": credential.mailbox_address,
                "microsoft_tenant_status": "present" if credential.microsoft_tenant_id else "absent",
                "granted_scopes": credential.scopes.split(),
                "connector_health_status": credential.connector_health_status,
                "reauthorization_required": credential.reauthorization_required,
                "last_error_summary": credential.last_error_summary,
                "last_successful_sync_at": credential.last_successful_sync_at.isoformat() if credential.last_successful_sync_at else None,
                "last_refresh_at": credential.last_refresh_at.isoformat() if credential.last_refresh_at else None,
                "last_refresh_status": credential.last_refresh_status,
                "connected_at": credential.connected_at.isoformat() if credential.connected_at else None,
                "disconnected_at": credential.disconnected_at.isoformat() if credential.disconnected_at else None,
            }

    def delete(self) -> None:
        with SessionLocal.begin() as session:
            credential = self._row(session)
            if credential is not None:
                credential.disconnected_at = datetime.now(timezone.utc)
                credential.reauthorization_required = True
                credential.connector_health_status = "disconnected"
                credential.updated_at = datetime.now(timezone.utc)

    @staticmethod
    def _fernet() -> Fernet:
        from os import getenv

        key = getenv("POLARIS_OUTLOOK_TOKEN_ENCRYPTION_KEY")
        if not key:
            raise OutlookCredentialError(
                "Outlook token encryption is not configured. Missing POLARIS_OUTLOOK_TOKEN_ENCRYPTION_KEY"
            )
        try:
            return Fernet(key.encode("utf-8"))
        except (TypeError, ValueError) as exc:
            raise OutlookCredentialError("POLARIS_OUTLOOK_TOKEN_ENCRYPTION_KEY is not a valid Fernet key") from exc

    @classmethod
    def _encrypt(cls, refresh_token: str) -> str:
        return cls._fernet().encrypt(refresh_token.encode("utf-8")).decode("utf-8")

    @classmethod
    def _decrypt(cls, encrypted_refresh_token: str) -> str:
        try:
            return cls._fernet().decrypt(encrypted_refresh_token.encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            raise OutlookCredentialError("Outlook credential encryption key is invalid") from exc

    def _row(self, session, *, for_update: bool = False) -> OutlookOAuthCredential | None:
        query = session.query(OutlookOAuthCredential).filter_by(organization_id=self.organization_id)
        if for_update:
            query = query.with_for_update()
        return query.one_or_none()
