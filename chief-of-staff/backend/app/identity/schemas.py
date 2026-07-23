"""Validated contracts for identities and organization memberships."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class IdentityCreate(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=200)


class IdentityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: EmailStr
    display_name: str
    status: str
    created_at: datetime
    updated_at: datetime


class MembershipCreate(BaseModel):
    identity_id: str = Field(min_length=1)
    role: Literal["owner", "admin", "member", "viewer"] = "member"


class MembershipRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    identity_id: str
    role: str
    status: str
    created_at: datetime
