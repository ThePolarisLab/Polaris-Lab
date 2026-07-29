"""Provider-neutral security contracts for Polaris."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol


class Permission(str, Enum):
    PLATFORM_ADMIN = "platform.admin"
    ORGANIZATION_READ = "organization.read"
    ORGANIZATION_WRITE = "organization.write"
    IDENTITY_READ = "identity.read"
    IDENTITY_WRITE = "identity.write"
    CONNECTOR_READ = "connector.read"
    CONNECTOR_WRITE = "connector.write"
    FINANCIAL_READ = "financial.read"
    FINANCIAL_WRITE = "financial.write"
    EXECUTIVE_READ = "executive.read"
    EXECUTIVE_WRITE = "executive.write"

    # Compatibility aliases for Phase 1 routes and tests that still use manage.
    ORGANIZATION_MANAGE = "organization.write"
    IDENTITY_MANAGE = "identity.write"
    CONNECTOR_MANAGE = "connector.write"


READ_PERMISSIONS = frozenset(
    {
        Permission.ORGANIZATION_READ,
        Permission.IDENTITY_READ,
        Permission.CONNECTOR_READ,
        Permission.FINANCIAL_READ,
        Permission.EXECUTIVE_READ,
    }
)

WRITE_PERMISSIONS = frozenset(
    {
        Permission.ORGANIZATION_WRITE,
        Permission.IDENTITY_WRITE,
        Permission.CONNECTOR_WRITE,
        Permission.FINANCIAL_WRITE,
        Permission.EXECUTIVE_WRITE,
    }
)


ROLE_PERMISSIONS: dict[str, frozenset[Permission]] = {
    "platform_admin": frozenset(Permission),
    "owner": READ_PERMISSIONS | WRITE_PERMISSIONS,
    "admin": READ_PERMISSIONS | WRITE_PERMISSIONS,
    "member": READ_PERMISSIONS,
    "viewer": frozenset(
        {
            Permission.ORGANIZATION_READ,
            Permission.CONNECTOR_READ,
            Permission.FINANCIAL_READ,
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
