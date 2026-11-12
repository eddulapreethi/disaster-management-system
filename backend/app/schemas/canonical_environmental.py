from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator

from app.utils.utc_timestamps import utc_isoformat

HazardIdentifier = Annotated[str, Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_]*$")]
SourceRecordIdentifier = str | int

HAZARD_TAXONOMY = {
    "flood": "Flood",
    "tropical_cyclone": "Cyclone, hurricane, or typhoon",
    "severe_storm": "Severe storm",
    "wildfire": "Wildfire",
    "heatwave": "Heatwave",
    "drought": "Drought",
    "earthquake": "Earthquake",
    "landslide": "Landslide",
    "glacial_lake_outburst_flood": "Glacial lake outburst flood (GLOF)",
}

RecordType = Literal[
    "observation",
    "forecast",
    "warning",
    "historical_event",
    "satellite_acquisition",
    "gis_reference",
]
QualityStatus = Literal[
    "VERIFIED",
    "UNVERIFIED",
    "STALE",
    "INVALID",
    "INCOMPLETE_METADATA",
    "ACCESS_BLOCKED",
    "UNSUPPORTED",
    "NOT_CHECKED",
]
FreshnessStatus = Literal["FRESH", "STALE", "UNAVAILABLE", "NOT_CHECKED"]
AvailabilityStatus = Literal[
    "AVAILABLE",
    "PARTIAL",
    "STALE",
    "ERROR",
    "UNVERIFIED",
    "ACCESS_BLOCKED",
    "UNSUPPORTED",
    "NOT_CHECKED",
    "NO_MATCHING_STORED_RECORDS",
    "NOT_PERSISTED",
    "REGIONAL",
]


class CanonicalModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WGS84Point(CanonicalModel):
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)


class WGS84BoundingBox(CanonicalModel):
    west: float = Field(ge=-180, le=180, allow_inf_nan=False)
    south: float = Field(ge=-90, le=90, allow_inf_nan=False)
    east: float = Field(ge=-180, le=180, allow_inf_nan=False)
    north: float = Field(ge=-90, le=90, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_bounds(self) -> WGS84BoundingBox:
        if self.south >= self.north:
            raise ValueError("Bounding-box south must be less than north.")
        return self

    @property
    def crosses_antimeridian(self) -> bool:
        return self.west > self.east


class CanonicalGeography(CanonicalModel):
    coordinate_reference_system: Literal["OGC:CRS84"] = "OGC:CRS84"
    requested_coordinates: WGS84Point | None = None
    provider_returned_coordinates: WGS84Point | None = None
    source_coordinates: WGS84Point | None = None
    requested_bbox: WGS84BoundingBox | None = None
    source_bbox: WGS84BoundingBox | None = None
    station_id: str | None = None
    station_id_is_internal: bool | None = None
    station_name: str | None = None
    coverage_scope: Literal["POINT", "REGIONAL", "UNKNOWN"] = "UNKNOWN"
    coverage_verified: bool = False
    coverage_limitations: list[str] = Field(default_factory=list)


class CanonicalTimestamps(CanonicalModel):
    source_timestamp_raw: str | None = None
    source_timezone: str | None = None
    timezone_assumption: str | None = None
    observation_time_utc: datetime | None = None
    event_time_utc: datetime | None = None
    forecast_issue_time_utc: datetime | None = None
    forecast_valid_time_utc: datetime | None = None
    forecast_lead_seconds: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    acquisition_time_utc: datetime | None = None
    retrieval_time_utc: datetime | None = None
    ingestion_time_utc: datetime | None = None

    @field_serializer(
        "observation_time_utc",
        "event_time_utc",
        "forecast_issue_time_utc",
        "forecast_valid_time_utc",
        "acquisition_time_utc",
        "retrieval_time_utc",
        "ingestion_time_utc",
        when_used="json",
    )
    def serialize_utc_time(self, value: datetime | None) -> str | None:
        return utc_isoformat(value)

    @model_validator(mode="after")
    def require_aware_utc_values(self) -> CanonicalTimestamps:
        for field_name in (
            "observation_time_utc",
            "event_time_utc",
            "forecast_issue_time_utc",
            "forecast_valid_time_utc",
            "acquisition_time_utc",
            "retrieval_time_utc",
            "ingestion_time_utc",
        ):
            value = getattr(self, field_name)
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise ValueError(f"{field_name} must be timezone-aware.")
            if value is not None and value.utcoffset().total_seconds() != 0:
                setattr(self, field_name, value.astimezone(timezone.utc))
        return self


class CanonicalSource(CanonicalModel):
    provider: str = Field(min_length=1, max_length=160)
    source_record_id: SourceRecordIdentifier | None = None
    source_dataset_id: str | None = None
    source_url: str | None = None
    attribution: str | None = None
    license_usage_status: Literal["VERIFIED", "UNVERIFIED", "RESTRICTED", "UNKNOWN"] = "UNKNOWN"
    license_usage_details: str | None = None
    transformation_metadata: dict[str, str] = Field(default_factory=dict)
    source_metadata: dict[str, object] = Field(default_factory=dict)


class CanonicalMeasurement(CanonicalModel):
    name: str = Field(min_length=1, max_length=120)
    source_value: float | str | None = None
    source_unit: str | None = None
    normalized_value: float | None = Field(default=None, allow_inf_nan=False)
    normalized_unit: str | None = None
    transformation: str | None = None


class ObservationPayload(CanonicalModel):
    kind: Literal["observation"] = "observation"
    measurement_basis: Literal["measured", "station_telemetry", "model_derived", "unknown"]
    measurements: list[CanonicalMeasurement] = Field(default_factory=list)


class ForecastPayload(CanonicalModel):
    kind: Literal["forecast"] = "forecast"
    model_or_product: str | None = None
    measurements: list[CanonicalMeasurement] = Field(default_factory=list)


class WarningPayload(CanonicalModel):
    kind: Literal["warning"] = "warning"
    warning_type: str | None = None
    severity: str | None = None
    issuing_authority: str | None = None
    valid_from_utc: datetime | None = None
    valid_to_utc: datetime | None = None


class HistoricalEventPayload(CanonicalModel):
    kind: Literal["historical_event"] = "historical_event"
    event_name: str | None = None
    event_description: str | None = None
    event_attributes: dict[str, object] = Field(default_factory=dict)


class SatelliteAcquisitionPayload(CanonicalModel):
    kind: Literal["satellite_acquisition"] = "satellite_acquisition"
    collection: str | None = None
    catalog_item_id: str | None = None
    bands: list[str] = Field(default_factory=list)
    output_format: str | None = None
    output_units: str | None = None
    process_result_pinned_to_catalog_item: bool | None = None


class GISReferencePayload(CanonicalModel):
    kind: Literal["gis_reference"] = "gis_reference"
    dataset_name: str | None = None
    layer_name: str | None = None
    feature_id: str | int | None = None
    geometry_type: str | None = None
    attributes: dict[str, object] = Field(default_factory=dict)


CanonicalPayload = (
    ObservationPayload
    | ForecastPayload
    | WarningPayload
    | HistoricalEventPayload
    | SatelliteAcquisitionPayload
    | GISReferencePayload
)

_PAYLOAD_TYPES = {
    "observation": ObservationPayload,
    "forecast": ForecastPayload,
    "warning": WarningPayload,
    "historical_event": HistoricalEventPayload,
    "satellite_acquisition": SatelliteAcquisitionPayload,
    "gis_reference": GISReferencePayload,
}


class CanonicalEnvironmentalRecord(CanonicalModel):
    contract_version: Literal["1.0"] = "1.0"
    local_record_id: str | int | None = None
    record_type: RecordType
    hazard_type: HazardIdentifier | None = None
    source: CanonicalSource
    timestamps: CanonicalTimestamps = Field(default_factory=CanonicalTimestamps)
    geography: CanonicalGeography = Field(default_factory=CanonicalGeography)
    quality_status: QualityStatus
    freshness_status: FreshnessStatus = "NOT_CHECKED"
    availability_status: AvailabilityStatus = "UNVERIFIED"
    validation_errors: list[str] = Field(default_factory=list)
    payload: CanonicalPayload

    @model_validator(mode="after")
    def validate_payload_type(self) -> CanonicalEnvironmentalRecord:
        if not isinstance(self.payload, _PAYLOAD_TYPES[self.record_type]):
            raise ValueError(f"Payload kind must match record_type {self.record_type!r}.")
        if self.record_type == "forecast":
            if self.timestamps.forecast_issue_time_utc is None:
                self.validation_errors.append("Forecast issue time is unavailable.")
            if self.timestamps.forecast_valid_time_utc is None:
                self.validation_errors.append("Forecast valid time is unavailable.")
        return self
