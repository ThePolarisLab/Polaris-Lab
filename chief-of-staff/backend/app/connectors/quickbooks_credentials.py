"""Encrypted persistence for Polaris-owned QuickBooks OAuth credentials."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base, SessionLocal


class QuickBooksCredentialError(RuntimeError):
    """Safe credential-store error that never includes secret values."""


@dataclass(frozen=True)
class StoredQuickBooksCredential:
    """Decrypted credential material plus safe operational metadata."""

    organization_id: str
    realm_id: str
    refresh_token: str
    scopes: str
    verified_company_name: str | None
    company_verified_at: datetime | None
    verification_status: str
    connector_health_status: str
    reauthorization_required: bool
    last_error_summary: str | None
    last_successful_sync_at: datetime | None
    last_refresh_at: datetime | None
    last_refresh_status: str | None


class QuickBooksOAuthCredential(Base):
    """QuickBooks OAuth credentials for one authenticated organization."""

    __tablename__ = "quickbooks_oauth_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String, ForeignKey("organizations.id"), nullable=False, unique=True, index=True
    )
    realm_id: Mapped[str] = mapped_column(String(80))
    encrypted_refresh_token: Mapped[str] = mapped_column(Text)
    scopes: Mapped[str] = mapped_column(Text, default="com.intuit.quickbooks.accounting")
    verified_company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    company_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verification_status: Mapped[str] = mapped_column(String(40), default="unverified")
    connector_health_status: Mapped[str] = mapped_column(String(60), default="authorization_required")
    reauthorization_required: Mapped[bool] = mapped_column(Boolean, default=False)
    last_error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_successful_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_refresh_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_refresh_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    connected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    organization = relationship("Organization")


class QuickBooksOAuthState(Base):
    """Single-use QuickBooks OAuth initiation state bound to a Polaris principal."""

    __tablename__ = "quickbooks_oauth_states"

    state: Mapped[str] = mapped_column(String(255), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String, ForeignKey("organizations.id"), nullable=False, index=True)
    identity_id: Mapped[str] = mapped_column(String, ForeignKey("identities.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    organization = relationship("Organization")
    identity = relationship("Identity")


class QuickBooksCredentialStore:
    """Read and rotate encrypted QuickBooks refresh tokens in Polaris storage."""

    def __init__(self, organization_id: str) -> None:
        if not organization_id:
            raise QuickBooksCredentialError("QuickBooks organization context is required")
        self.organization_id = organization_id

    def save(self, *, realm_id: str, refresh_token: str, scopes: str) -> None:
        if not realm_id or not refresh_token:
            raise QuickBooksCredentialError("QuickBooks OAuth credentials are incomplete")
        encrypted = self._encrypt(refresh_token)
        with SessionLocal.begin() as session:
            credential = self._row(session)
            now = datetime.now(timezone.utc)
            if credential is None:
                credential = QuickBooksOAuthCredential(
                    organization_id=self.organization_id,
                    realm_id=realm_id,
                    encrypted_refresh_token=encrypted,
                    scopes=scopes,
                    verification_status="unverified",
                    connector_health_status="connected_unverified",
                    reauthorization_required=False,
                    connected_at=now,
                    updated_at=now,
                )
                session.add(credential)
            else:
                credential.realm_id = realm_id
                credential.encrypted_refresh_token = encrypted
                credential.scopes = scopes
                credential.verification_status = "unverified"
                credential.connector_health_status = "connected_unverified"
                credential.reauthorization_required = False
                credential.last_error_summary = None
                credential.updated_at = now

    def load(self) -> tuple[str, str]:
        credential = self.load_credential()
        return credential.realm_id, credential.refresh_token

    def load_credential(self) -> StoredQuickBooksCredential:
        with SessionLocal() as session:
            credential = self._row(session)
            if credential is None:
                raise QuickBooksCredentialError(
                    "QuickBooks has not been authorized through the Polaris OAuth flow"
                )
            refresh_token = self._decrypt(credential.encrypted_refresh_token)
            return StoredQuickBooksCredential(
                organization_id=credential.organization_id,
                realm_id=credential.realm_id,
                refresh_token=refresh_token,
                scopes=credential.scopes,
                verified_company_name=credential.verified_company_name,
                company_verified_at=credential.company_verified_at,
                verification_status=credential.verification_status,
                connector_health_status=credential.connector_health_status,
                reauthorization_required=credential.reauthorization_required,
                last_error_summary=credential.last_error_summary,
                last_successful_sync_at=credential.last_successful_sync_at,
                last_refresh_at=credential.last_refresh_at,
                last_refresh_status=credential.last_refresh_status,
            )

    def rotate_refresh_token(self, *, realm_id: str, refresh_token: str, scopes: str | None = None) -> None:
        if not realm_id or not refresh_token:
            raise QuickBooksCredentialError("QuickBooks refresh token rotation returned incomplete credentials")
        encrypted = self._encrypt(refresh_token)
        now = datetime.now(timezone.utc)
        with SessionLocal.begin() as session:
            credential = self._row(session, for_update=True)
            if credential is None:
                raise QuickBooksCredentialError("QuickBooks credential disappeared during token rotation")
            credential.realm_id = realm_id
            credential.encrypted_refresh_token = encrypted
            if scopes:
                credential.scopes = scopes
            credential.last_refresh_at = now
            credential.last_refresh_status = "success"
            credential.reauthorization_required = False
            credential.connector_health_status = credential.connector_health_status or "connected_unverified"
            credential.updated_at = now

    def record_refresh_failure(self, message: str, *, reauthorization_required: bool = False) -> None:
        self.update_metadata(
            connector_health_status="reauthorization_required" if reauthorization_required else "degraded",
            reauthorization_required=reauthorization_required,
            last_refresh_status="failed",
            last_error_summary=message,
        )

    def record_verification(
        self,
        *,
        status: str,
        company_name: str | None = None,
        error_summary: str | None = None,
    ) -> None:
        values: dict[str, object] = {
            "verification_status": status,
            "connector_health_status": status,
            "last_error_summary": error_summary,
        }
        if status == "healthy" and company_name:
            values["verified_company_name"] = company_name
            values["company_verified_at"] = datetime.now(timezone.utc)
            values["reauthorization_required"] = False
        self.update_metadata(**values)

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
        try:
            credential = self.load_credential()
        except QuickBooksCredentialError:
            return {
                "authorized": False,
                "verification_status": "authorization_required",
                "connector_health_status": "authorization_required",
                "reauthorization_required": True,
            }
        return {
            "authorized": True,
            "verified_company_name": credential.verified_company_name,
            "company_verified_at": credential.company_verified_at.isoformat() if credential.company_verified_at else None,
            "verification_status": credential.verification_status,
            "connector_health_status": credential.connector_health_status,
            "reauthorization_required": credential.reauthorization_required,
            "last_error_summary": credential.last_error_summary,
            "last_successful_sync_at": credential.last_successful_sync_at.isoformat() if credential.last_successful_sync_at else None,
            "last_refresh_at": credential.last_refresh_at.isoformat() if credential.last_refresh_at else None,
            "last_refresh_status": credential.last_refresh_status,
        }

    def delete(self) -> None:
        with SessionLocal.begin() as session:
            credential = self._row(session)
            if credential is not None:
                session.delete(credential)

    @staticmethod
    def _fernet() -> Fernet:
        from os import getenv

        key = getenv("POLARIS_QBO_TOKEN_ENCRYPTION_KEY")
        if not key:
            raise QuickBooksCredentialError(
                "QuickBooks token encryption is not configured. Missing "
                "POLARIS_QBO_TOKEN_ENCRYPTION_KEY"
            )
        try:
            return Fernet(key.encode("utf-8"))
        except (TypeError, ValueError) as exc:
            raise QuickBooksCredentialError(
                "POLARIS_QBO_TOKEN_ENCRYPTION_KEY is not a valid Fernet key"
            ) from exc

    @classmethod
    def _encrypt(cls, refresh_token: str) -> str:
        return cls._fernet().encrypt(refresh_token.encode("utf-8")).decode("utf-8")

    @classmethod
    def _decrypt(cls, encrypted_refresh_token: str) -> str:
        try:
            return cls._fernet().decrypt(encrypted_refresh_token.encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            raise QuickBooksCredentialError(
                "QuickBooks credential encryption key is invalid"
            ) from exc

    def _row(self, session, *, for_update: bool = False) -> QuickBooksOAuthCredential | None:
        query = session.query(QuickBooksOAuthCredential).filter_by(organization_id=self.organization_id)
        if for_update:
            query = query.with_for_update()
        return query.one_or_none()
