from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.database import Base


class KnowledgeRelationship(Base):
    __tablename__ = "knowledge_relationships"
    __table_args__ = (
        UniqueConstraint(
            "source",
            "target",
            "relation",
            name="uq_knowledge_relationship",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )
    source: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    target: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    relation: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
