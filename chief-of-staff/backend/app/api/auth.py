"""Security foundation API."""

from collections.abc import Generator

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.database import SessionLocal
from app.events import ConnectorEvent, EventActor, EventSource, EventSubject, event_bus
from app.security.dependencies import get_principal
from app.security.models import AuthenticatedPrincipal
from app.security.providers import LocalTokenProvider
from app.security.service import AuthenticationError, AuthorizationError, SecurityService


router = APIRouter(prefix="/api/v1/auth", tags=["security"])


class LocalLoginRequest(BaseModel):
    identity_id: str = Field(min_length=1)
    organization_id: str = Field(min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 3600


class PrincipalResponse(BaseModel):
    identity_id: str
    organization_id: str
    membership_id: str
    role: str
    permissions: list[str]
    provider: str


def get_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@router.post("/local/token", response_model=TokenResponse)
def issue_local_token(
    request: LocalLoginRequest,
    session: Session = Depends(get_session),
) -> TokenResponse:
    if settings.environment.lower() not in {"development", "test"}:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")

    provider = LocalTokenProvider()
    token = provider.issue(request.identity_id)
    try:
        principal = SecurityService(session).authenticate(
            provider, token, request.organization_id
        )
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except AuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    event_bus.publish(
        ConnectorEvent(
            event_type="identity.authentication.succeeded.v1",
            organization_id=principal.organization_id,
            tenant_id=principal.organization_id,
            source=EventSource(service="security-kernel"),
            actor=EventActor(actor_type="identity", actor_id=principal.identity_id),
            subject=EventSubject(subject_type="membership", subject_id=principal.membership_id),
            idempotency_key=f"auth:{principal.identity_id}:{principal.organization_id}:{token[-12:]}",
            payload={"provider": principal.provider, "role": principal.role},
        )
    )
    return TokenResponse(access_token=token)


@router.get("/me", response_model=PrincipalResponse)
def me(principal: AuthenticatedPrincipal = Depends(get_principal)) -> PrincipalResponse:
    return PrincipalResponse(
        identity_id=principal.identity_id,
        organization_id=principal.organization_id,
        membership_id=principal.membership_id,
        role=principal.role,
        permissions=sorted(item.value for item in principal.permissions),
        provider=principal.provider,
    )
