from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, Float, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.connection import Base


class WeatherObservation(Base):
    __tablename__ = "weather_observations"
    __table_args__ = (
        CheckConstraint("latitude BETWEEN -90 AND 90", name="ck_weather_latitude"),
        CheckConstraint("longitude BETWEEN -180 AND 180", name="ck_weather_longitude"),
        CheckConstraint("humidity_percent IS NULL OR humidity_percent BETWEEN 0 AND 100", name="ck_weather_humidity"),
        CheckConstraint("precipitation_mm IS NULL OR precipitation_mm >= 0", name="ck_weather_precipitation"),
        CheckConstraint("rain_mm IS NULL OR rain_mm >= 0", name="ck_weather_rain"),
        CheckConstraint("wind_speed_kmh IS NULL OR wind_speed_kmh >= 0", name="ck_weather_wind"),
        UniqueConstraint("station_id", "observation_time", "source", name="uq_weather_station_source_time"),
        Index("ix_weather_station_observation", "station_id", "observation_time"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    station_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    station_name: Mapped[str] = mapped_column(String(160), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="open-meteo")
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    humidity_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    precipitation_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    rain_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_speed_kmh: Mapped[float | None] = mapped_column(Float, nullable=True)
    pressure_hpa: Mapped[float | None] = mapped_column(Float, nullable=True)
    observation_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
