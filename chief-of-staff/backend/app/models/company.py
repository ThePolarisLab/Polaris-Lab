from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.database.database import Base


class Company(Base):
    __tablename__ = "company"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=False, unique=True, index=True)

    company_name = Column(String)
    owner = Column(String)
    headquarters = Column(String)
    country = Column(String)

    organization = relationship("Organization")