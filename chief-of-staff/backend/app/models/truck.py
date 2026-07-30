from sqlalchemy import Column, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database.database import Base


class Truck(Base):
    __tablename__ = "trucks"
    __table_args__ = (
        UniqueConstraint("organization_id", "unit_number", name="uq_truck_organization_unit"),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=False, index=True)
    unit_number = Column(String, index=True)
    make = Column(String)
    model = Column(String)
    year = Column(Integer)
    vin = Column(String)
    plate = Column(String)
    status = Column(String)

    organization = relationship("Organization")