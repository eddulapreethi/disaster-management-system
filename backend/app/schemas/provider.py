from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from app.utils.utc_timestamps import utc_isoformat

CoverageStatus = Literal[
    "SUPPORTED",
    "UNSUPPORTED",
    "STALE",
    "UNAVAILABLE",
    "UNVERIFIED",
]
FreshnessStatus = Literal["READY", "STALE", "UNAVAILABLE", "ERROR", "UNVERIFIED"]


def coverage_status_from_freshness(freshness_status: str) -> CoverageStatus:
    if freshness_status == "READY":
        return "SUPPORTED"
    if freshness_status == "STALE":
        return "STALE"
    if freshness_status in {"UNAVAILABLE", "ERROR"}:
        return "UNAVAILABLE"
    return "UNVERIFIED"


class ProviderLocation(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    station_id: str | None = None
    station_id_is_internal: bool | None = None
    region: str | None = None
    country: str | None = None


class ProviderProvenance(BaseModel):
    provider: str
    product: str | None = None
    source_record_id: str | int | None = None
    location: ProviderLocation
    observation_time: datetime | None = None
    fetched_at: datetime | None = None
    units: dict[str, str] = Field(default_factory=dict)
    freshness_status: FreshnessStatus
    provider_metadata: dict[str, Any] = Field(default_factory=dict)

    @field_serializer("observation_time", "fetched_at", when_used="json")
    def serialize_timestamp(self, value: datetime | None) -> str | None:
        return utc_isoformat(value)


class ProviderCoverage(BaseModel):
    provider: str
    product: str
    capability: str
    hazard: str | None = None
    status: CoverageStatus
    scope: str
    details: str
    checked_at: datetime
    latitude: float
    longitude: float

    @field_serializer("checked_at", when_used="json")
    def serialize_checked_at(self, value: datetime) -> str:
        return utc_isoformat(value) or ""


class LocationCoverageResponse(BaseModel):
    coordinate_reference_system: Literal["OGC:CRS84"] = "OGC:CRS84"
    latitude: float
    longitude: float
    checked_at: datetime
    providers: list[ProviderCoverage]

    @field_serializer("checked_at", when_used="json")
    def serialize_checked_at(self, value: datetime) -> str:
        return utc_isoformat(value) or ""
