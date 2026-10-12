from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, computed_field, field_serializer

from app.utils.utc_timestamps import utc_isoformat

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

    @field_serializer("observation_time", "fetched_at", when_used="json")
    def serialize_utc_timestamp(self, value: datetime) -> str:
        return utc_isoformat(value) or ""

    @computed_field
    @property
    def measurement_units(self) -> dict[str, str]:
        return {"water_level": "m", "rainfall": "mm"}


class HydrologySourceStatus(BaseModel):
    source: str
    resource_id: str
    status: ReadinessStatus
    freshness_status: ReadinessStatus
    collection_status: str
    message: str | None
    last_observation: datetime | None
    observation_age_seconds: int | None
    last_fetch: datetime | None
    station_id: str | None
    latest_station: str | None
    update_frequency: str
    stale_after_hours: int
    water_level: float | None
    water_level_unit: str | None = None
    discharge: float | None
    rainfall: float | None
    rainfall_unit: str | None = None
    records_received: int
    records_returned: int
    valid_records: int
    inserted_count: int
    duplicates_skipped: int
    parse_errors: int
    newer_observation_found: bool
    latest_error: str | None

    @field_serializer("last_observation", "last_fetch", when_used="json")
    def serialize_utc_timestamp(self, value: datetime | None) -> str | None:
        return utc_isoformat(value)


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
    historical_data: dict[str, Any]
    features: dict[str, Any]
    ml_model: dict[str, Any]
    prediction: dict[str, Any]

    @field_serializer("checked_at", when_used="json")
    def serialize_checked_at(self, value: datetime) -> str:
        return utc_isoformat(value) or ""
