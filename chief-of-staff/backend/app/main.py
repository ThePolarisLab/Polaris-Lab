from fastapi import Depends, FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.database.schema_guard import health_database_status, prepare_database_for_runtime
from app.security.dependencies import require_permission
from app.security.models import Permission

# API Routers
from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.code_understanding import router as code_understanding_router
from app.api.company import router as company_router
from app.api.connectors import router as connectors_router
from app.api.dashboard import router as dashboard_router
from app.api.events import router as events_router
from app.api.github_engine import router as github_engine_router
from app.api.identity import router as identity_router
from app.api.memory import router as memory_router
from app.api.memory_search import router as memory_search_router
from app.api.missions import router as missions_router
from app.api.organizations import router as organizations_router
from app.api.quickbooks_financials import router as quickbooks_financials_router
from app.api.quickbooks_oauth import router as quickbooks_oauth_router
from app.api.reasoning import router as reasoning_router
from app.api.refactoring import router as refactoring_router
from app.api.relationships import router as relationships_router
from app.api.system import router as system_router
from app.api.team_notes import router as team_notes_router
from app.api.truck import router as truck_router
from app.api.work_context import router as work_context_router
from app.connectors.github import GitHubConnector
from app.connectors.quickbooks import QuickBooksConnector
from app.connectors.registry import connector_registry

prepare_database_for_runtime()
connector_registry.register(GitHubConnector(), replace=True)
connector_registry.register(QuickBooksConnector(), replace=True)

app = FastAPI(title=settings.service_name, version=settings.version)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

organization_read = [Depends(require_permission(Permission.ORGANIZATION_READ))]
executive_read = [Depends(require_permission(Permission.EXECUTIVE_READ))]

app.include_router(company_router, dependencies=organization_read)
app.include_router(truck_router)
app.include_router(memory_router, dependencies=executive_read)
app.include_router(chat_router, dependencies=executive_read)
app.include_router(missions_router, dependencies=executive_read)
app.include_router(relationships_router, dependencies=executive_read)
app.include_router(memory_search_router, dependencies=executive_read)
app.include_router(reasoning_router, dependencies=executive_read)
app.include_router(team_notes_router, dependencies=executive_read)
app.include_router(dashboard_router, dependencies=executive_read)
app.include_router(github_engine_router)
app.include_router(code_understanding_router, dependencies=[Depends(require_permission(Permission.CONNECTOR_READ))])
app.include_router(refactoring_router, dependencies=[Depends(require_permission(Permission.CONNECTOR_READ))])
app.include_router(work_context_router, dependencies=executive_read)
app.include_router(system_router)
app.include_router(connectors_router)
app.include_router(quickbooks_oauth_router)
app.include_router(quickbooks_financials_router)
app.include_router(events_router, dependencies=organization_read)
app.include_router(organizations_router)
app.include_router(identity_router)
app.include_router(auth_router)


@app.get("/")
def root():
    return {
        "service": settings.service_name,
        "version": settings.version,
        "environment": settings.environment,
        "organization": settings.organization_slug,
        "database": "Connected",
        "capabilities": [
            "EXP-014B Work Context Engine",
            "PGE-002 Repository Intelligence",
            "PGE-003 Code Understanding Engine",
            "PGE-004.1 Complexity Engine",
            "PGE-008.1 Connector SDK",
            "PGE-008.1 Connector Event Bus",
            "PGE-008.2 GitHub Connector",
            "PGE-008.3 Canonical Event Contract",
            "PGE-008.4A Organization Foundation",
            "PGE-008.4B Identity and Membership",
            "PGE-008.4C Authentication and Authorization",
            "PGE-009.6B QuickBooks Connector Registration",
            "PGE-009.6C Polaris QuickBooks OAuth and Token Storage",
            "PGE-009.6G QuickBooks Financial API Foundation",
            "PGE-009.6H Financial Snapshot Engine",
            "PGE-009.6I Executive Financial Dashboard",
        ],
    }


@app.get("/health", tags=["runtime"])
def health(response: Response):
    database_status = health_database_status()
    if database_status != "connected":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "ok" if database_status == "connected" else "degraded",
        "service": settings.service_name,
        "version": settings.version,
        "environment": settings.environment,
        "organization": settings.organization_slug,
        "checks": {
            "api": "ready",
            "database": database_status,
        },
    }
