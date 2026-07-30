"""Encrypted persistence for Polaris-owned QuickBooks OAuth credentials."""

from __future__ import annotations

from datetime import datetime, timezone

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base, SessionLocal


class QuickBooksCredentialError(RuntimeError):
    """Safe credential-store error that never includes secret values."""


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
        encrypted = self._fernet().encrypt(refresh_token.encode("utf-8")).decode("utf-8")
        with SessionLocal() as session:
            credential = (
                session.query(QuickBooksOAuthCredential)
                .filter_by(organization_id=self.organization_id)
                .one_or_none()
            )
            if credential is None:
                credential = QuickBooksOAuthCredential(
                    organization_id=self.organization_id,
                    realm_id=realm_id,
                    encrypted_refresh_token=encrypted,
                    scopes=scopes,
                )
                session.add(credential)
            else:
                credential.realm_id = realm_id
                credential.encrypted_refresh_token = encrypted
                credential.scopes = scopes
                credential.updated_at = datetime.now(timezone.utc)
            session.commit()

    def load(self) -> tuple[str, str]:
        with SessionLocal() as session:
            credential = (
                session.query(QuickBooksOAuthCredential)
                .filter_by(organization_id=self.organization_id)
                .one_or_none()
            )
            if credential is None:
                raise QuickBooksCredentialError(
                    "QuickBooks has not been authorized through the Polaris OAuth flow"
                )
            try:
                refresh_token = self._fernet().decrypt(
                    credential.encrypted_refresh_token.encode("utf-8")
                ).decode("utf-8")
            except InvalidToken as exc:
                raise QuickBooksCredentialError(
                    "QuickBooks credential encryption key is invalid"
                ) from exc
            return credential.realm_id, refresh_token

    def delete(self) -> None:
        with SessionLocal() as session:
            credential = (
                session.query(QuickBooksOAuthCredential)
                .filter_by(organization_id=self.organization_id)
                .one_or_none()
            )
            if credential is not None:
                session.delete(credential)
                session.commit()

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
