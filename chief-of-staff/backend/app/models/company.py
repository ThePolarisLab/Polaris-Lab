from sqlalchemy import Column, Integer, String

from app.database.database import Base


class Company(Base):
    __tablename__ = "company"

    id = Column(Integer, primary_key=True, index=True)

    company_name = Column(String)
    owner = Column(String)
    headquarters = Column(String)
    country = Column(String)