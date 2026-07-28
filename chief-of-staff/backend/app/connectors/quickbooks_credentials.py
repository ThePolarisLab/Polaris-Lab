"""Encrypted persistence for Polaris-owned QuickBooks OAuth credentials."""

from __future__ import annotations

import os
from datetime import datetime, timezone

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.database import Base, SessionLocal


class QuickBooksCredentialError(RuntimeError):
    """Safe credential-store error that never includes secret values."""


class QuickBooksOAuthCredential(Base):
    """Single-tenant QuickBooks OAuth state for the active Polaris organization."""

    __tablename__ = "quickbooks_oauth_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    organization_slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
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


class QuickBooksCredentialStore:
    """Read and rotate encrypted QuickBooks refresh tokens in Polaris storage."""

    def __init__(self, organization_slug: str | None = None) -> None:
        self.organization_slug = organization_slug or os.getenv(
            "POLARIS_ORGANIZATION_SLUG", "mor-logistics"
        )

    def save(self, *, realm_id: str, refresh_token: str, scopes: str) -> None:
        if not realm_id or not refresh_token:
            raise QuickBooksCredentialError("QuickBooks OAuth credentials are incomplete")
        encrypted = self._fernet().encrypt(refresh_token.encode("utf-8")).decode("utf-8")
        with SessionLocal() as session:
            credential = (
                session.query(QuickBooksOAuthCredential)
                .filter_by(organization_slug=self.organization_slug)
                .one_or_none()
            )
            if credential is None:
                credential = QuickBooksOAuthCredential(
                    organization_slug=self.organization_slug,
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
                .filter_by(organization_slug=self.organization_slug)
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
                .filter_by(organization_slug=self.organization_slug)
                .one_or_none()
            )
            if credential is not None:
                session.delete(credential)
                session.commit()

    @staticmethod
    def _fernet() -> Fernet:
        key = os.getenv("POLARIS_QBO_TOKEN_ENCRYPTION_KEY")
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
