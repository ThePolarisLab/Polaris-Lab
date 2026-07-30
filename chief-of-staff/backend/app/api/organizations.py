"""Organization boundary API."""

from collections.abc import Generator

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database.database import SessionLocal
from app.events import ConnectorEvent, EventActor, EventSource, EventSubject, event_bus
from app.organizations.schemas import OrganizationCreate, OrganizationRead
from app.organizations.service import OrganizationConflictError, OrganizationService
from app.security.dependencies import require_organization_path_match, require_permission
from app.security.models import AuthenticatedPrincipal, Permission


router = APIRouter(prefix="/api/v1/organizations", tags=["organizations"])

organization_manage = Depends(require_permission(Permission.ORGANIZATION_MANAGE))


def get_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@router.post("", response_model=OrganizationRead, status_code=status.HTTP_201_CREATED, dependencies=[organization_manage])
def create_organization(
    request: OrganizationCreate,
    session: Session = Depends(get_session),
) -> OrganizationRead:
    service = OrganizationService(session)
    try:
        organization = service.create(request)
    except OrganizationConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    event_bus.publish(
        ConnectorEvent(
            event_type="organization.organization.created.v1",
            organization_id=organization.id,
            tenant_id=organization.id,
            source=EventSource(service="organization-service"),
            actor=EventActor(actor_type="system", actor_id="bootstrap-api"),
            subject=EventSubject(
                subject_type="organization",
                subject_id=organization.id,
            ),
            idempotency_key=f"organization:{organization.id}:created:v1",
            payload={
                "slug": organization.slug,
                "display_name": organization.display_name,
                "status": organization.status,
            },
        )
    )
    return OrganizationRead.model_validate(organization)


@router.get("", response_model=list[OrganizationRead], dependencies=[organization_manage])
def list_organizations(session: Session = Depends(get_session)) -> list[OrganizationRead]:
    return [
        OrganizationRead.model_validate(item)
        for item in OrganizationService(session).list()
    ]


@router.get("/{organization_id}", response_model=OrganizationRead, dependencies=[organization_manage])
def get_organization(
    organization_id: str,
    principal: AuthenticatedPrincipal = Depends(require_organization_path_match),
    session: Session = Depends(get_session),
) -> OrganizationRead:
    organization = OrganizationService(session).get(organization_id)
    if organization is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="organization not found",
        )
    return OrganizationRead.model_validate(organization)
