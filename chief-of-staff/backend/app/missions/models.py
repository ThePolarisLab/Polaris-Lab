from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database.database import Base

def utc_now():
    return datetime.now(timezone.utc)

class Mission(Base):
    __tablename__ = "missions"
    __table_args__ = (UniqueConstraint("organization_id", "code", name="uq_mission_organization_code"),)

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=False, index=True)
    code = Column(String, index=True, nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False, default="")
    status = Column(String, nullable=False, default="Not Started")
    priority = Column(String, nullable=False, default="Medium")
    owner = Column(String, nullable=False, default="Founder")
    company = Column(String, nullable=False, default="MOR Logistics Manitoba Limited")
    progress = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    started_at = Column(DateTime, nullable=True)
    due_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    organization = relationship("Organization")
    workflows = relationship("Workflow", back_populates="mission", cascade="all, delete-orphan", order_by="Workflow.position")

class Workflow(Base):
    __tablename__ = "mission_workflows"
    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=False, index=True)
    mission_id = Column(Integer, ForeignKey("missions.id"), nullable=False, index=True)
    title = Column(String, nullable=False)
    status = Column(String, nullable=False, default="Not Started")
    progress = Column(Integer, nullable=False, default=0)
    position = Column(Integer, nullable=False, default=0)
    organization = relationship("Organization")
    mission = relationship("Mission", back_populates="workflows")
    tasks = relationship("MissionTask", back_populates="workflow", cascade="all, delete-orphan", order_by="MissionTask.position")

class MissionTask(Base):
    __tablename__ = "mission_tasks"
    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=False, index=True)
    workflow_id = Column(Integer, ForeignKey("mission_workflows.id"), nullable=False, index=True)
    title = Column(String, nullable=False)
    status = Column(String, nullable=False, default="Not Started")
    position = Column(Integer, nullable=False, default=0)
    system = Column(String, nullable=True)
    capability = Column(String, nullable=True)
    notes = Column(Text, nullable=False, default="")
    completed_at = Column(DateTime, nullable=True)
    organization = relationship("Organization")
    workflow = relationship("Workflow", back_populates="tasks")
