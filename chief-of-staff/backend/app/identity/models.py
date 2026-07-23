"""Persistence models for vendor-neutral identities and organization membership."""

from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, String, UniqueConstraint

from app.database.database import Base


class IdentityStatus(str, Enum):
    """Lifecycle state for a human identity."""

    ACTIVE = "active"
    SUSPENDED = "suspended"
    DISABLED = "disabled"


class MembershipRole(str, Enum):
    """Initial organization roles; permissions remain a later concern."""

    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class MembershipStatus(str, Enum):
    """Lifecycle state for an organization membership."""

    ACTIVE = "active"
    SUSPENDED = "suspended"
    REVOKED = "revoked"


class Identity(Base):
    """Vendor-neutral person identity independent of authentication providers."""

    __tablename__ = "identities"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()), index=True)
    email = Column(String, nullable=False, unique=True, index=True)
    display_name = Column(String, nullable=False)
    status = Column(String, nullable=False, default=IdentityStatus.ACTIVE.value)
    created_at = Column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class OrganizationMembership(Base):
    """Explicit relationship between one identity and one organization."""

    __tablename__ = "organization_memberships"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "identity_id", name="uq_membership_organization_identity"
        ),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid4()), index=True)
    organization_id = Column(
        String, ForeignKey("organizations.id"), nullable=False, index=True
    )
    identity_id = Column(String, ForeignKey("identities.id"), nullable=False, index=True)
    role = Column(String, nullable=False, default=MembershipRole.MEMBER.value)
    status = Column(String, nullable=False, default=MembershipStatus.ACTIVE.value)
    created_at = Column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
