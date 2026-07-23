"""Application service for identities and organization memberships."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.identity.models import Identity, OrganizationMembership
from app.identity.schemas import IdentityCreate, MembershipCreate
from app.organizations.models import Organization


class IdentityConflictError(ValueError):
    """Raised when identity or membership uniqueness is violated."""


class IdentityNotFoundError(ValueError):
    """Raised when a referenced identity or organization does not exist."""


class IdentityService:
    """Manage identities and explicit tenant memberships."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create_identity(self, request: IdentityCreate) -> Identity:
        email = request.email.lower().strip()
        if self._session.query(Identity).filter(Identity.email == email).first():
            raise IdentityConflictError(f"identity email '{email}' already exists")

        identity = Identity(email=email, display_name=request.display_name.strip())
        self._session.add(identity)
        self._session.commit()
        self._session.refresh(identity)
        return identity

    def get_identity(self, identity_id: str) -> Identity | None:
        return self._session.query(Identity).filter(Identity.id == identity_id).first()

    def add_membership(
        self, organization_id: str, request: MembershipCreate
    ) -> OrganizationMembership:
        organization = (
            self._session.query(Organization)
            .filter(Organization.id == organization_id)
            .first()
        )
        if organization is None:
            raise IdentityNotFoundError("organization not found")

        identity = self.get_identity(request.identity_id)
        if identity is None:
            raise IdentityNotFoundError("identity not found")

        membership = OrganizationMembership(
            organization_id=organization_id,
            identity_id=identity.id,
            role=request.role,
        )
        self._session.add(membership)
        try:
            self._session.commit()
        except IntegrityError as exc:
            self._session.rollback()
            raise IdentityConflictError("membership already exists") from exc
        self._session.refresh(membership)
        return membership

    def list_memberships(self, organization_id: str) -> list[OrganizationMembership]:
        return (
            self._session.query(OrganizationMembership)
            .filter(OrganizationMembership.organization_id == organization_id)
            .order_by(OrganizationMembership.created_at, OrganizationMembership.id)
            .all()
        )
