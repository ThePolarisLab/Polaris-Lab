from sqlalchemy import Column, Integer, String

from app.database.database import Base


class Truck(Base):
    __tablename__ = "trucks"

    id = Column(Integer, primary_key=True, index=True)
    unit_number = Column(String, unique=True, index=True)
    make = Column(String)
    model = Column(String)
    year = Column(Integer)
    vin = Column(String)
    plate = Column(String)
    status = Column(String)