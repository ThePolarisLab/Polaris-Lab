"""Authenticated runtime information endpoints."""

from datetime import datetime, timezone
import os
import time

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text

from app.core.config import settings
from app.database.database import engine
from app.security.dependencies import require_permission
from app.security.models import Permission

router = APIRouter(prefix="/api/v1/system", tags=["builder-system"])
_STARTED_AT = time.time()
_system_read = Depends(require_permission(Permission.CONNECTOR_READ))


def _database_status() -> str:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        return "unavailable"
    return "connected"


@router.get("/health", dependencies=[_system_read])
def system_health(response: Response):
    """Return authenticated API and database readiness for operators."""
    database_status = _database_status()
    if database_status != "connected":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "ok" if database_status == "connected" else "degraded",
        "checks": {
            "api": "ready",
            "database": database_status,
        },
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/info", dependencies=[_system_read])
def system_info():
    """Return authenticated non-secret runtime metadata for operational visibility."""
    return {
        "service": settings.service_name,
        "environment": settings.environment,
        "organization": settings.organization_slug,
        "started_at": datetime.fromtimestamp(_STARTED_AT, timezone.utc).isoformat(),
        "uptime_seconds": max(0, int(time.time() - _STARTED_AT)),
        "git_commit": os.getenv("POLARIS_GIT_COMMIT", "unknown"),
    }


@router.get("/version", dependencies=[_system_read])
def system_version():
    """Return the authenticated Polaris build identity."""
    return {
        "version": settings.version,
        "git_commit": os.getenv("POLARIS_GIT_COMMIT", "unknown"),
    }
