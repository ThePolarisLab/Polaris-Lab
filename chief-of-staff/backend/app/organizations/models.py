"""Persistence model for Polaris organization boundaries."""

from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from sqlalchemy import Column, DateTime, String

from app.database.database import Base


class OrganizationStatus(str, Enum):
    """Lifecycle state for a Polaris organization."""

    ACTIVE = "active"
    SUSPENDED = "suspended"
    ARCHIVED = "archived"


class Organization(Base):
    """Top-level tenant and authorization boundary in Polaris."""

    __tablename__ = "organizations"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()), index=True)
    slug = Column(String, nullable=False, unique=True, index=True)
    display_name = Column(String, nullable=False)
    legal_name = Column(String, nullable=True)
    status = Column(String, nullable=False, default=OrganizationStatus.ACTIVE.value)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
