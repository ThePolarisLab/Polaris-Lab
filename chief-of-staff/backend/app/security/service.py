"""Authentication normalization and deny-by-default authorization."""

from sqlalchemy.orm import Session

from app.identity.models import Identity, IdentityStatus, MembershipStatus, OrganizationMembership
from app.security.models import (
    AuthenticatedPrincipal,
    AuthenticationProvider,
    Permission,
    ROLE_PERMISSIONS,
)


class AuthenticationError(ValueError):
    """Raised when credentials cannot be authenticated."""


class AuthorizationError(PermissionError):
    """Raised when an authenticated principal lacks authority."""


class SecurityService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def authenticate(
        self,
        provider: AuthenticationProvider,
        credential: str,
        organization_id: str,
    ) -> AuthenticatedPrincipal:
        result = provider.validate(credential)
        identity = (
            self._session.query(Identity)
            .filter(Identity.id == result.subject)
            .first()
        )
        if identity is None or identity.status != IdentityStatus.ACTIVE.value:
            raise AuthenticationError("identity is not active")

        membership = (
            self._session.query(OrganizationMembership)
            .filter(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.identity_id == identity.id,
            )
            .first()
        )
        if membership is None or membership.status != MembershipStatus.ACTIVE.value:
            raise AuthorizationError("active organization membership required")

        permissions = ROLE_PERMISSIONS.get(membership.role, frozenset())
        return AuthenticatedPrincipal(
            identity_id=identity.id,
            organization_id=organization_id,
            membership_id=membership.id,
            role=membership.role,
            permissions=permissions,
            provider=result.provider,
            subject=result.subject,
            claims=result.claims,
        )

    @staticmethod
    def require(principal: AuthenticatedPrincipal, permission: Permission) -> None:
        if not principal.has_permission(permission):
            raise AuthorizationError(f"permission required: {permission.value}")
