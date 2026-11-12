from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_serializer

from app.schemas.canonical_environmental import (
    CanonicalEnvironmentalRecord,
    WGS84BoundingBox,
)
from app.utils.utc_timestamps import utc_isoformat


class EarthquakeEventQueryFilters(BaseModel):
    bbox: WGS84BoundingBox
    start_time: datetime
    end_time: datetime
    min_magnitude: float | None = Field(default=None, ge=-10, le=10, allow_inf_nan=False)
    max_magnitude: float | None = Field(default=None, ge=-10, le=10, allow_inf_nan=False)
    review_status: Literal["automatic", "reviewed"] | None = None
    limit: int = Field(ge=1, le=500)

    @field_serializer("start_time", "end_time", when_used="json")
    def serialize_time(self, value: datetime) -> str:
        return utc_isoformat(value) or ""


class EarthquakeEventQueryResponse(BaseModel):
    provider: Literal["USGS ComCat"] = "USGS ComCat"
    attribution: str = "U.S. Geological Survey (USGS) ComCat"
    license_usage_status: Literal["UNKNOWN"] = "UNKNOWN"
    license_usage_details: str = (
        "Contributor and product redistribution terms have not been verified."
    )
    retrieved_at: datetime
    freshness_status: Literal["NOT_ASSESSED"] = "NOT_ASSESSED"
    data_status: Literal["AVAILABLE", "NO_MATCHING_EVENTS"]
    filters: EarthquakeEventQueryFilters
    returned_events: int = Field(ge=0, le=500)
    records: list[CanonicalEnvironmentalRecord]

    @field_serializer("retrieved_at", when_used="json")
    def serialize_retrieved_at(self, value: datetime) -> str:
        return utc_isoformat(value) or ""
