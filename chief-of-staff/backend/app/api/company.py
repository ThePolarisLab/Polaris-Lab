from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.database import SessionLocal
from app.models.company import Company

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/company")
def get_company(db: Session = Depends(get_db)):
    company = db.query(Company).first()

    if company is None:
        company = Company(
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
        "company_name": company.company_name,
        "owner": company.owner,
        "headquarters": company.headquarters,
        "country": company.country,
    }