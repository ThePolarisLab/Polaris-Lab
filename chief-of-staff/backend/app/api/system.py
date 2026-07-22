"""Builder-facing runtime information endpoints."""

from datetime import datetime, timezone
import os
import time

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.core.config import settings
from app.database.database import engine

router = APIRouter(prefix="/api/v1/system", tags=["builder-system"])
_STARTED_AT = time.time()


def _database_status() -> str:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        return "unavailable"
    return "connected"


@router.get("/health")
def system_health(response: Response):
    """Return API and database readiness for the Builder Console."""
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


@router.get("/info")
def system_info():
    """Return non-secret runtime metadata for operational visibility."""
    return {
        "service": settings.service_name,
        "environment": settings.environment,
        "organization": settings.organization_slug,
        "started_at": datetime.fromtimestamp(_STARTED_AT, timezone.utc).isoformat(),
        "uptime_seconds": max(0, int(time.time() - _STARTED_AT)),
        "git_commit": os.getenv("POLARIS_GIT_COMMIT", "unknown"),
    }


@router.get("/version")
def system_version():
    """Return the deployed Polaris build identity."""
    return {
        "version": settings.version,
        "git_commit": os.getenv("POLARIS_GIT_COMMIT", "unknown"),
    }
