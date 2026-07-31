"""Production authentication persistence models."""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text, UniqueConstraint

from app.database.database import Base


class ProductionPasswordCredential(Base):
    """Hashed password credential for an identity."""

    __tablename__ = "production_password_credentials"

    identity_id = Column(String, ForeignKey("identities.id"), primary_key=True, nullable=False)
    password_hash = Column(Text, nullable=False)
    algorithm = Column(String(length=40), nullable=False, default="bcrypt")
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class ProductionAuthSession(Base):
    """Refresh-token backed authenticated session."""

    __tablename__ = "production_auth_sessions"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()), index=True)
    identity_id = Column(String, ForeignKey("identities.id"), nullable=False, index=True)
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=False, index=True)
    refresh_token_hash = Column(String(length=128), nullable=False, unique=True, index=True)
    rotated_from_session_id = Column(String, nullable=True)
    user_agent = Column(Text, nullable=True)
    ip_address = Column(String(length=120), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    access_expires_at = Column(DateTime(timezone=True), nullable=False)
    refresh_expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    revoke_reason = Column(String(length=120), nullable=True)


class ProductionAuthBootstrapState(Base):
    """One-time production bootstrap completion marker."""

    __tablename__ = "production_auth_bootstrap_state"

    id = Column(String, primary_key=True, nullable=False, default="first-admin")
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=False)
    identity_id = Column(String, ForeignKey("identities.id"), nullable=False)
    completed = Column(Boolean, nullable=False, default=True)
    completed_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class ProductionLoginAttempt(Base):
    """Login attempt audit/rate-limit record."""

    __tablename__ = "production_login_attempts"
    __table_args__ = (
        UniqueConstraint("id", name="uq_production_login_attempt_id"),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid4()), nullable=False)
    email = Column(String(length=320), nullable=False, index=True)
    ip_address = Column(String(length=120), nullable=True, index=True)
    succeeded = Column(Boolean, nullable=False, default=False)
    failure_reason = Column(String(length=120), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
