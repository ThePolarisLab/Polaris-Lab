"""Validated API contracts for organization management."""

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.organizations.models import OrganizationStatus


_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class OrganizationCreate(BaseModel):
    slug: str = Field(min_length=2, max_length=80)
    display_name: str = Field(min_length=1, max_length=160)
    legal_name: str | None = Field(default=None, max_length=200)

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not _SLUG_PATTERN.fullmatch(normalized):
            raise ValueError("slug must contain lowercase letters, numbers, and hyphens")
        return normalized


class OrganizationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    slug: str
    display_name: str
    legal_name: str | None
    status: OrganizationStatus
    created_at: datetime
    updated_at: datetime
