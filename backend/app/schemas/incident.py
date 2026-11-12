from datetime import datetime, timezone
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator, model_validator

from app.utils.utc_timestamps import utc_isoformat

HazardCategory = Literal[
    "flood",
    "cyclone",
    "storm",
    "wildfire",
    "heatwave",
    "drought",
    "earthquake",
    "landslide",
    "other",
]
IncidentStatus = Literal["pending", "verified", "rejected", "needs_review"]


class EvidenceMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_name: str = Field(min_length=1, max_length=180)
    media_type: str = Field(
        min_length=3,
        max_length=100,
        pattern=r"^[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+$",
    )
    size_bytes: int = Field(ge=0, le=25_000_000)
    sha256: str | None = Field(default=None, pattern=r"^[a-fA-F0-9]{64}$")

    @field_validator("file_name")
    @classmethod
    def validate_file_name(cls, value: str) -> str:
        normalized = value.strip()
        has_path_separator = any(character in normalized for character in ("/", "\\", "\x00"))
        has_control_character = any(ord(character) < 32 or ord(character) == 127 for character in normalized)
        if not normalized or normalized in {".", ".."} or has_path_separator or has_control_character:
            raise ValueError("Evidence file names must be plain names without paths.")
        return normalized


class IncidentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=3, max_length=160)
    hazard_category: HazardCategory
    description: str = Field(min_length=10, max_length=4000)
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    incident_time: datetime
    incident_timezone: str = Field(min_length=1, max_length=64)
    evidence_metadata: list[EvidenceMetadata] = Field(default_factory=list, max_length=5)

    @field_validator("title", "description", "incident_timezone")
    @classmethod
    def strip_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("This field must not be blank.")
        return normalized

    @model_validator(mode="after")
    def validate_incident_time(self):
        try:
            zone = ZoneInfo(self.incident_timezone)
        except ZoneInfoNotFoundError as error:
            raise ValueError("incident_timezone must be a recognized IANA timezone.") from error

        value = self.incident_time
        if value.tzinfo is None or value.utcoffset() is None:
            first = value.replace(tzinfo=zone, fold=0)
            second = value.replace(tzinfo=zone, fold=1)
            first_round_trip = first.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None)
            second_round_trip = second.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None)
            if first_round_trip != value or second_round_trip != value:
                raise ValueError("incident_time falls in a nonexistent local-time interval.")
            if first.utcoffset() != second.utcoffset():
                raise ValueError("Ambiguous local incident times must include an explicit UTC offset.")
            value = first
        elif value.astimezone(zone).utcoffset() != value.utcoffset():
            raise ValueError("incident_time offset does not match incident_timezone.")

        self.incident_time = value.astimezone(timezone.utc)
        return self


class IncidentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=3, max_length=160)
    description: str | None = Field(default=None, min_length=10, max_length=4000)
    latitude: float | None = Field(default=None, ge=-90, le=90, allow_inf_nan=False)
    longitude: float | None = Field(default=None, ge=-180, le=180, allow_inf_nan=False)
    evidence_metadata: list[EvidenceMetadata] | None = Field(default=None, max_length=5)

    @field_validator("title", "description")
    @classmethod
    def validate_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip()
        if not normalized:
            raise ValueError("This field must not be blank.")
        return normalized

    @model_validator(mode="after")
    def require_fields(self):
        if not self.model_fields_set:
            raise ValueError("At least one editable field is required.")
        for field in ("title", "description", "latitude", "longitude", "evidence_metadata"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null.")
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Provide both latitude and longitude when changing coordinates.")
        return self


class IncidentReviewCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: IncidentStatus
    note: str | None = Field(default=None, max_length=1000)

    @field_validator("note")
    @classmethod
    def normalize_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def require_reason_for_rejection_or_review(self):
        if self.status in {"rejected", "needs_review"} and not self.note:
            raise ValueError("A review note is required for rejected or needs-review decisions.")
        return self


class IncidentRead(BaseModel):
    id: int
    title: str
    hazard_category: HazardCategory
    description: str
    latitude: float
    longitude: float
    incident_time: datetime
    incident_timezone: str
    submitted_at: datetime
    status: IncidentStatus
    source: str
    provenance: dict[str, str]
    can_edit: bool
    can_review: bool
    can_view_private: bool

    @field_serializer("incident_time", "submitted_at", when_used="json")
    def serialize_time(self, value: datetime) -> str:
        return utc_isoformat(value) or ""


class IncidentReviewRead(BaseModel):
    reviewer_id: int
    reviewer_name: str
    previous_status: IncidentStatus
    new_status: IncidentStatus
    note: str | None
    created_at: datetime

    @field_serializer("created_at", when_used="json")
    def serialize_created_at(self, value: datetime) -> str:
        return utc_isoformat(value) or ""


class IncidentDetailRead(IncidentRead):
    evidence_metadata: list[EvidenceMetadata]
    review_history: list[IncidentReviewRead]
    reporter_id: int


class IncidentPagination(BaseModel):
    limit: int
    offset: int
    returned_records: int
    total_matching_records: int


class IncidentListRead(BaseModel):
    records: list[IncidentRead]
    pagination: IncidentPagination
    has_more: bool


class IncidentCount(BaseModel):
    key: str
    count: int


class IncidentDailyCount(BaseModel):
    date: str
    count: int


class IncidentAnalyticsRead(BaseModel):
    total_reports: int
    by_hazard: list[IncidentCount]
    by_status: list[IncidentCount]
    by_day: list[IncidentDailyCount]
    records_without_verified_region: int
    region_breakdown_status: Literal["NOT_AVAILABLE"]
    disclaimer: str
