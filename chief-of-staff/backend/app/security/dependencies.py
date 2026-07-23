"""FastAPI dependencies for tenant-bound authentication and authorization."""

from collections.abc import Callable, Generator

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.database.database import SessionLocal
from app.security.models import AuthenticatedPrincipal, Permission
from app.security.providers import LocalTokenProvider
from app.security.service import AuthenticationError, AuthorizationError, SecurityService


def get_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def get_principal(
    authorization: str | None = Header(default=None),
    organization_id: str | None = Header(default=None, alias="X-Polaris-Organization"),
    session: Session = Depends(get_session),
) -> AuthenticatedPrincipal:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="bearer credential required")
    if not organization_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="organization header required")
    try:
        return SecurityService(session).authenticate(
            LocalTokenProvider(), authorization.removeprefix("Bearer ").strip(), organization_id
        )
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except AuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


def require_permission(permission: Permission) -> Callable[..., AuthenticatedPrincipal]:
    def dependency(
        principal: AuthenticatedPrincipal = Depends(get_principal),
    ) -> AuthenticatedPrincipal:
        try:
            SecurityService.require(principal, permission)
        except AuthorizationError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
        return principal

    return dependency
