from datetime import date

from fastapi import APIRouter, Depends, Query

from app.motive.fault_lifecycle_tenant import certify_fault_lifecycle_for_organization
from app.security.dependencies import require_permission
from app.security.models import AuthenticatedPrincipal, Permission

router = APIRouter(prefix="/api/v1/motive/fault-lifecycle", tags=["motive"])


@router.get("")
def fault_lifecycle_evidence(
    date_value: date = Query(..., alias="date"),
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.CONNECTOR_READ)),
):
    return certify_fault_lifecycle_for_organization(
        organization_id=principal.organization_id,
        certification_date=date_value,
    )
