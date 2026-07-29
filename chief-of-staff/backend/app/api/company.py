from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.database import SessionLocal
from app.models.company import Company
from app.security.dependencies import require_permission
from app.security.models import AuthenticatedPrincipal, Permission

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/company")
def get_company(
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.ORGANIZATION_READ)),
    db: Session = Depends(get_db),
):
    company = db.query(Company).filter(Company.organization_id == principal.organization_id).first()

    if company is None:
        company = Company(
            organization_id=principal.organization_id,
            company_name="MOR Logistics Manitoba Limited",
            owner="Surinder Pahil",
            headquarters="Winnipeg, Manitoba",
            country="Canada",
        )
        db.add(company)
        db.commit()
        db.refresh(company)

    return {
        "id": company.id,
        "organization_id": company.organization_id,
        "company_name": company.company_name,
        "owner": company.owner,
        "headquarters": company.headquarters,
        "country": company.country,
    }