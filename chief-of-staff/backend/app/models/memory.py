from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, Text

from app.database.database import Base


class MemoryEntry(Base):
    __tablename__ = "memory_entries"

    id = Column(Integer, primary_key=True, index=True)
    category = Column(String, nullable=False)
    title = Column(String, nullable=False)
    details = Column(Text, nullable=False)
    importance = Column(String, nullable=False, default="Medium")
    source = Column(String, nullable=False, default="Manual")
    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )