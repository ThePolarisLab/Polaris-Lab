"""Minimized latest durable Motive vehicle observation; no raw payloads."""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.database import Base


class MotiveLocationObservation(Base):
    __tablename__ = "motive_location_observations"
    __table_args__ = (UniqueConstraint("organization_id", "vehicle_id", name="uq_motive_location_org_vehicle"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[str] = mapped_column(String, ForeignKey("organizations.id"), index=True)
    vehicle_id: Mapped[int] = mapped_column(Integer, ForeignKey("motive_vehicles.id"), index=True)
    truck_number: Mapped[str | None] = mapped_column(String(120))
    city: Mapped[str | None] = mapped_column(String(255))
    province: Mapped[str | None] = mapped_column(String(120))
    country: Mapped[str | None] = mapped_column(String(120))
    location_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Lookup is authoritative for current DRIVER only, not trailer attachment.
    current_driver_name: Mapped[str | None] = mapped_column(String(255))
    pairing_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    signal_status: Mapped[str] = mapped_column(String(40))
