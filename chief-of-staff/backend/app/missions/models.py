from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from app.database.database import Base

def utc_now():
    return datetime.now(timezone.utc)

class Mission(Base):
    __tablename__ = "missions"
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True, nullable=False)
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
    workflows = relationship("Workflow", back_populates="mission", cascade="all, delete-orphan", order_by="Workflow.position")

class Workflow(Base):
    __tablename__ = "mission_workflows"
    id = Column(Integer, primary_key=True, index=True)
    mission_id = Column(Integer, ForeignKey("missions.id"), nullable=False, index=True)
    title = Column(String, nullable=False)
    status = Column(String, nullable=False, default="Not Started")
    progress = Column(Integer, nullable=False, default=0)
    position = Column(Integer, nullable=False, default=0)
    mission = relationship("Mission", back_populates="workflows")
    tasks = relationship("MissionTask", back_populates="workflow", cascade="all, delete-orphan", order_by="MissionTask.position")

class MissionTask(Base):
    __tablename__ = "mission_tasks"
    id = Column(Integer, primary_key=True, index=True)
    workflow_id = Column(Integer, ForeignKey("mission_workflows.id"), nullable=False, index=True)
    title = Column(String, nullable=False)
    status = Column(String, nullable=False, default="Not Started")
    position = Column(Integer, nullable=False, default=0)
    system = Column(String, nullable=True)
    capability = Column(String, nullable=True)
    notes = Column(Text, nullable=False, default="")
    completed_at = Column(DateTime, nullable=True)
    workflow = relationship("Workflow", back_populates="tasks")
