"""Security foundation and production authentication API."""

from collections.abc import Generator
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.service import (
    BOOTSTRAP_IDENTITY_ID,
    BOOTSTRAP_ORGANIZATION_ID,
    BootstrapConfigurationError,
    BootstrapUnavailableError,
    ProductionAuthService,
    RateLimitError,
    is_managed_environment,
)
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


class BootstrapRequest(BaseModel):
    bootstrap_secret: str = Field(min_length=1)
    password: str = Field(min_length=12, max_length=256)


class BootstrapStatusResponse(BaseModel):
    available: bool
    organization_id: str = BOOTSTRAP_ORGANIZATION_ID
    identity_id: str = BOOTSTRAP_IDENTITY_ID


class BootstrapResponse(BaseModel):
    status: str = "completed"
    organization_id: str
    identity_id: str


class PasswordLoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=256)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 3600


class SessionTokenResponse(TokenResponse):
    refresh_token: str
    refresh_expires_in: int
    organization_id: str


class LogoutResponse(BaseModel):
    revoked: bool = True


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


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    if forwarded:
        return forwarded[:120]
    return request.client.host[:120] if request.client else None


def _user_agent(request: Request) -> str | None:
    value = request.headers.get("user-agent")
    return value[:500] if value else None


@router.get("/bootstrap/status", response_model=BootstrapStatusResponse)
def bootstrap_status(session: Session = Depends(get_session)) -> BootstrapStatusResponse:
    available = ProductionAuthService(session).bootstrap_available()
    return BootstrapStatusResponse(available=available)


@router.post("/bootstrap", response_model=BootstrapResponse, status_code=status.HTTP_201_CREATED)
def bootstrap_first_admin(
    payload: BootstrapRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> BootstrapResponse:
    service = ProductionAuthService(session)
    try:
        with session.begin():
            result = service.complete_bootstrap(
                bootstrap_secret=payload.bootstrap_secret,
                password=payload.password,
                ip_address=_client_ip(request),
            )
    except BootstrapConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="bootstrap is not configured") from exc
    except BootstrapUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return BootstrapResponse(**result)


@router.post("/login", response_model=SessionTokenResponse)
def login(
    payload: PasswordLoginRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> SessionTokenResponse:
    service = ProductionAuthService(session)
    try:
        with session.begin():
            tokens = service.login(
                email=payload.email,
                password=payload.password,
                ip_address=_client_ip(request),
                user_agent=_user_agent(request),
            )
    except RateLimitError as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="too many failed login attempts") from exc
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except AuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return SessionTokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        organization_id=tokens.organization_id,
        expires_in=tokens.expires_in,
        refresh_expires_in=tokens.refresh_expires_in,
    )


@router.post("/refresh", response_model=SessionTokenResponse)
def refresh(
    payload: RefreshRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> SessionTokenResponse:
    service = ProductionAuthService(session)
    try:
        with session.begin():
            tokens = service.refresh(
                refresh_token=payload.refresh_token,
                ip_address=_client_ip(request),
                user_agent=_user_agent(request),
            )
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    return SessionTokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        organization_id=tokens.organization_id,
        expires_in=tokens.expires_in,
        refresh_expires_in=tokens.refresh_expires_in,
    )


@router.post("/logout", response_model=LogoutResponse)
def logout(
    authorization: str | None = Header(default=None),
    session: Session = Depends(get_session),
) -> LogoutResponse:
    if not authorization or not authorization.startswith("Bearer "):
        return LogoutResponse(revoked=True)
    try:
        with session.begin():
            ProductionAuthService(session).logout_access_token(authorization.removeprefix("Bearer ").strip())
    except AuthenticationError:
        return LogoutResponse(revoked=True)
    return LogoutResponse(revoked=True)


@router.post("/local/token", response_model=TokenResponse)
def issue_local_token(request: LocalLoginRequest, session: Session = Depends(get_session)) -> TokenResponse:
    if settings.environment.lower() not in {"development", "test"} or is_managed_environment():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")

    provider = LocalTokenProvider()
    token = provider.issue(request.identity_id)
    try:
        principal = SecurityService(session).authenticate(provider, token, request.organization_id)
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
            idempotency_key=f"auth:{principal.identity_id}:{principal.organization_id}:{uuid4()}",
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