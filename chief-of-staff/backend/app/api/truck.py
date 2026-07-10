from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database.database import SessionLocal
from app.models.truck import Truck

router = APIRouter()


class TruckCreate(BaseModel):
    unit_number: str
    make: str
    model: str
    year: int
    vin: str | None = None
    plate: str | None = None
    status: str = "Available"


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/trucks")
def get_trucks(db: Session = Depends(get_db)):
    trucks = db.query(Truck).all()

    return [
        {
            "id": truck.id,
            "unit_number": truck.unit_number,
            "make": truck.make,
            "model": truck.model,
            "year": truck.year,
            "vin": truck.vin,
            "plate": truck.plate,
            "status": truck.status,
        }
        for truck in trucks
    ]


@router.post("/trucks")
def create_truck(
    truck_data: TruckCreate,
    db: Session = Depends(get_db),
):
    truck = Truck(
        unit_number=truck_data.unit_number,
        make=truck_data.make,
        model=truck_data.model,
        year=truck_data.year,
        vin=truck_data.vin,
        plate=truck_data.plate,
        status=truck_data.status,
    )

    db.add(truck)
    db.commit()
    db.refresh(truck)

    return {
        "id": truck.id,
        "unit_number": truck.unit_number,
        "make": truck.make,
        "model": truck.model,
        "year": truck.year,
        "vin": truck.vin,
        "plate": truck.plate,
        "status": truck.status,
    }