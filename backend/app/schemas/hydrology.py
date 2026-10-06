from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ReadinessStatus = Literal["READY", "STALE", "UNAVAILABLE", "ERROR", "NOT_READY"]


class HydrologicalObservationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source: str
    source_resource_id: str
    source_record_id: int
    station_id: str
    station_name: str
    river_name: str | None
    state_name: str | None
    district_name: str | None
    latitude: float | None
    longitude: float | None
    water_level: float | None
    discharge: float | None
    rainfall: float | None
    observation_time: datetime
    fetched_at: datetime


class HydrologySourceStatus(BaseModel):
    source: str
    resource_id: str
    status: ReadinessStatus
    message: str | None
    last_observation: datetime | None
    last_fetch: datetime | None
    latest_station: str | None
    water_level: float | None
    discharge: float | None
    rainfall: float | None
    records_received: int
    inserted_count: int
    duplicates_skipped: int
    parse_errors: int


class HydrologyStatusResponse(BaseModel):
    source: str = "NWDP/NWIC CWC telemetry"
    status: ReadinessStatus
    poll_interval_seconds: int
    stale_after_hours: int
    sources: list[HydrologySourceStatus]
    message: str


class DataReadinessResponse(BaseModel):
    checked_at: datetime
    sources: dict[str, dict[str, Any]]
    features: dict[str, Any]
    ml_model: dict[str, Any]
    prediction: dict[str, Any]
