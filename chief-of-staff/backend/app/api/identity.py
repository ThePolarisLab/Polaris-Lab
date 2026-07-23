"""Identity and organization membership API."""

from collections.abc import Generator

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database.database import SessionLocal
from app.events import ConnectorEvent, EventActor, EventSource, EventSubject, event_bus
from app.identity.schemas import (
    IdentityCreate,
    IdentityRead,
    MembershipCreate,
    MembershipRead,
)
from app.identity.service import (
    IdentityConflictError,
    IdentityNotFoundError,
    IdentityService,
)


router = APIRouter(prefix="/api/v1", tags=["identity"])


def get_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@router.post("/identities", response_model=IdentityRead, status_code=status.HTTP_201_CREATED)
def create_identity(
    request: IdentityCreate,
    session: Session = Depends(get_session),
) -> IdentityRead:
    service = IdentityService(session)
    try:
        identity = service.create_identity(request)
    except IdentityConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    event_bus.publish(
        ConnectorEvent(
            event_type="identity.identity.created.v1",
            source=EventSource(service="identity-service"),
            actor=EventActor(actor_type="system", actor_id="identity-api"),
            subject=EventSubject(subject_type="identity", subject_id=identity.id),
            idempotency_key=f"identity:{identity.id}:created:v1",
            payload={
                "email": identity.email,
                "display_name": identity.display_name,
                "status": identity.status,
            },
        )
    )
    return IdentityRead.model_validate(identity)


@router.get("/identities/{identity_id}", response_model=IdentityRead)
def get_identity(
    identity_id: str,
    session: Session = Depends(get_session),
) -> IdentityRead:
    identity = IdentityService(session).get_identity(identity_id)
    if identity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="identity not found")
    return IdentityRead.model_validate(identity)


@router.post(
    "/organizations/{organization_id}/memberships",
    response_model=MembershipRead,
    status_code=status.HTTP_201_CREATED,
)
def add_membership(
    organization_id: str,
    request: MembershipCreate,
    session: Session = Depends(get_session),
) -> MembershipRead:
    service = IdentityService(session)
    try:
        membership = service.add_membership(organization_id, request)
    except IdentityNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except IdentityConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    event_bus.publish(
        ConnectorEvent(
            event_type="identity.membership.created.v1",
            organization_id=membership.organization_id,
            tenant_id=membership.organization_id,
            source=EventSource(service="identity-service"),
            actor=EventActor(actor_type="system", actor_id="membership-api"),
            subject=EventSubject(subject_type="membership", subject_id=membership.id),
            idempotency_key=f"membership:{membership.id}:created:v1",
            payload={
                "identity_id": membership.identity_id,
                "role": membership.role,
                "status": membership.status,
            },
        )
    )
    return MembershipRead.model_validate(membership)


@router.get(
    "/organizations/{organization_id}/memberships",
    response_model=list[MembershipRead],
)
def list_memberships(
    organization_id: str,
    session: Session = Depends(get_session),
) -> list[MembershipRead]:
    return [
        MembershipRead.model_validate(item)
        for item in IdentityService(session).list_memberships(organization_id)
    ]
