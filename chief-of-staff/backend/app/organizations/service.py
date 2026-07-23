"""Application service for organization lifecycle operations."""

from sqlalchemy.orm import Session

from app.organizations.models import Organization
from app.organizations.schemas import OrganizationCreate


class OrganizationConflictError(ValueError):
    """Raised when an organization violates a uniqueness boundary."""


class OrganizationService:
    """Create and retrieve organizations without exposing persistence details."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, request: OrganizationCreate) -> Organization:
        existing = (
            self._session.query(Organization)
            .filter(Organization.slug == request.slug)
            .first()
        )
        if existing is not None:
            raise OrganizationConflictError(
                f"organization slug '{request.slug}' already exists"
            )

        organization = Organization(
            slug=request.slug,
            display_name=request.display_name.strip(),
            legal_name=request.legal_name.strip() if request.legal_name else None,
        )
        self._session.add(organization)
        self._session.commit()
        self._session.refresh(organization)
        return organization

    def list(self) -> list[Organization]:
        return self._session.query(Organization).order_by(Organization.slug).all()

    def get(self, organization_id: str) -> Organization | None:
        return (
            self._session.query(Organization)
            .filter(Organization.id == organization_id)
            .first()
        )
