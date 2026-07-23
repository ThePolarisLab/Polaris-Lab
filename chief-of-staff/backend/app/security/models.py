"""Provider-neutral security contracts for Polaris."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol


class Permission(str, Enum):
    ORGANIZATION_READ = "organization.read"
    ORGANIZATION_MANAGE = "organization.manage"
    IDENTITY_READ = "identity.read"
    IDENTITY_MANAGE = "identity.manage"
    CONNECTOR_READ = "connector.read"
    CONNECTOR_MANAGE = "connector.manage"
    EXECUTIVE_READ = "executive.read"


ROLE_PERMISSIONS: dict[str, frozenset[Permission]] = {
    "owner": frozenset(Permission),
    "admin": frozenset(
        {
            Permission.ORGANIZATION_READ,
            Permission.ORGANIZATION_MANAGE,
            Permission.IDENTITY_READ,
            Permission.IDENTITY_MANAGE,
            Permission.CONNECTOR_READ,
            Permission.CONNECTOR_MANAGE,
            Permission.EXECUTIVE_READ,
        }
    ),
    "member": frozenset(
        {
            Permission.ORGANIZATION_READ,
            Permission.IDENTITY_READ,
            Permission.CONNECTOR_READ,
            Permission.EXECUTIVE_READ,
        }
    ),
    "viewer": frozenset(
        {
            Permission.ORGANIZATION_READ,
            Permission.CONNECTOR_READ,
            Permission.EXECUTIVE_READ,
        }
    ),
}


@dataclass(frozen=True)
class AuthenticationResult:
    provider: str
    subject: str
    claims: dict[str, Any] = field(default_factory=dict)


class AuthenticationProvider(Protocol):
    name: str

    def validate(self, credential: str) -> AuthenticationResult:
        """Validate an external credential and return normalized identity evidence."""


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    identity_id: str
    organization_id: str
    membership_id: str
    role: str
    permissions: frozenset[Permission]
    provider: str
    subject: str
    claims: dict[str, Any] = field(default_factory=dict)

    def has_permission(self, permission: Permission) -> bool:
        return permission in self.permissions
