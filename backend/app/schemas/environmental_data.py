from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_serializer

from app.schemas.canonical_environmental import CanonicalEnvironmentalRecord
from app.utils.utc_timestamps import utc_isoformat

DataCategory = Literal[
    "weather_observation",
    "hydrological_observation",
    "disaster_event_report",
]


class EnvironmentalDataRecord(BaseModel):
    category: DataCategory
    record_id: int
    provider: str
    source_record_id: str | int | None
    measurement_category: str | None = None
    hazard: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    geographic_metadata: dict[str, Any]
    observation_time: datetime | None = None
    event_time: datetime | None = None
    event_timezone: str | None = None
    fetched_at: datetime | None = None
    ingested_at: datetime | None = None
    reported_at: datetime | None = None
    values: dict[str, float | str | None]
    units: dict[str, str]
    raw_source_values: dict[str, Any]
    quality_status: Literal["VALIDATED_SHAPE", "PARTIAL", "INVALID", "UNVERIFIED"]
    freshness_status: Literal["READY", "STALE", "ERROR", "UNVERIFIED"]
    validation_findings: list[str]
    attribution: str | None = None
    license_metadata: str | None = None
    duplicate_key: bool = False
    conflicting_values: bool = False
    canonical_record: CanonicalEnvironmentalRecord | None = None

    @field_serializer("observation_time", "event_time", "fetched_at", "ingested_at", "reported_at", when_used="json")
    def serialize_timestamp(self, value: datetime | None) -> str | None:
        return utc_isoformat(value)


class EnvironmentalDataSourceStatus(BaseModel):
    category: str
    status: Literal[
        "AVAILABLE",
        "PARTIAL",
        "STALE",
        "ERROR",
        "UNVERIFIED",
        "NO_MATCHING_STORED_RECORDS",
        "NOT_PERSISTED",
        "REGIONAL",
    ]
    provider: str | None
    details: str
    matching_records: int = Field(
        description="Matching records in this returned page only; not a query-wide or provider total."
    )
    count_scope: Literal["RETURNED_PAGE"] = "RETURNED_PAGE"


class EnvironmentalDataPagination(BaseModel):
    limit: int
    offset: int
    returned_records: int
    count_scope: Literal["RETURNED_PAGE"] = "RETURNED_PAGE"


class EnvironmentalDataResponse(BaseModel):
    checked_at: datetime
    coordinate_reference_system: Literal["OGC:CRS84"] = "OGC:CRS84"
    records: list[EnvironmentalDataRecord]
    sources: list[EnvironmentalDataSourceStatus]
    filters: dict[str, Any]
    pagination: EnvironmentalDataPagination
    has_more: bool

    @field_serializer("checked_at", when_used="json")
    def serialize_checked_at(self, value: datetime) -> str:
        return utc_isoformat(value) or ""
