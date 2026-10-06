from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.connection import Base


class HydrologicalObservation(Base):
    __tablename__ = "hydrological_observations"
    __table_args__ = (
        CheckConstraint("latitude IS NULL OR latitude BETWEEN -90 AND 90", name="ck_hydro_latitude"),
        CheckConstraint("longitude IS NULL OR longitude BETWEEN -180 AND 180", name="ck_hydro_longitude"),
        UniqueConstraint(
            "source_resource_id",
            "station_id",
            "observation_time",
            name="uq_hydro_source_station_observation",
        ),
        UniqueConstraint(
            "source_resource_id",
            "source_record_id",
            name="uq_hydro_source_record",
        ),
        Index("ix_hydro_station_observation", "station_id", "observation_time"),
        Index("ix_hydro_source_fetched", "source", "fetched_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    source: Mapped[str] = mapped_column(String(120), nullable=False)
    source_resource_id: Mapped[str] = mapped_column(String(80), nullable=False)
    source_record_id: Mapped[int] = mapped_column(Integer, nullable=False)
    station_id: Mapped[str] = mapped_column(String(64), nullable=False)
    station_name: Mapped[str] = mapped_column(String(200), nullable=False)
    river_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    state_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    district_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    water_level: Mapped[float | None] = mapped_column(Float, nullable=True)
    discharge: Mapped[float | None] = mapped_column(Float, nullable=True)
    rainfall: Mapped[float | None] = mapped_column(Float, nullable=True)
    observation_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
