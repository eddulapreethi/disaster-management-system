from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal, Mapping, NamedTuple

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CONTRACT_VERSION = "1.1"
PROVIDER = "ECMWF/Copernicus CDS"
PRODUCT_DATASET_IDS = {
    "ERA5": "reanalysis-era5-single-levels",
    "ERA5-Land": "reanalysis-era5-land",
}
PRODUCT_RELEASE_STATUSES = {
    "ERA5": {"ERA5T", "FINAL", "UNKNOWN"},
    "ERA5-Land": {"ERA5_LAND_T", "CONSOLIDATED", "UNKNOWN"},
}
VariableRole = Literal[
    "ATMOSPHERIC_ANALYSIS",
    "LAND_MODEL_OUTPUT",
    "INTERPOLATED_ERA5_FORCING",
    "UNKNOWN",
]

ERA5_DOCUMENTATION = "https://confluence.ecmwf.int/display/CKB/ERA5%3A+data+documentation"
ERA5_LAND_DOCUMENTATION = "https://confluence.ecmwf.int/display/CKB/ERA5-Land%3A+data+documentation"


class VariableDefinition(NamedTuple):
    native_unit: str
    temporal_kind: Literal["instantaneous", "mean", "accumulation", "unknown"]
    role: VariableRole
    role_evidence_reference: str


VARIABLE_METADATA: dict[str, dict[str, VariableDefinition]] = {
    "ERA5": {
        "2m_temperature": VariableDefinition("K", "instantaneous", "ATMOSPHERIC_ANALYSIS", ERA5_DOCUMENTATION),
        "10m_u_component_of_wind": VariableDefinition("m s-1", "instantaneous", "ATMOSPHERIC_ANALYSIS", ERA5_DOCUMENTATION),
        "10m_v_component_of_wind": VariableDefinition("m s-1", "instantaneous", "ATMOSPHERIC_ANALYSIS", ERA5_DOCUMENTATION),
        "surface_pressure": VariableDefinition("Pa", "instantaneous", "ATMOSPHERIC_ANALYSIS", ERA5_DOCUMENTATION),
        "total_precipitation": VariableDefinition("m", "accumulation", "ATMOSPHERIC_ANALYSIS", ERA5_DOCUMENTATION),
    },
    "ERA5-Land": {
        "2m_temperature": VariableDefinition("K", "instantaneous", "INTERPOLATED_ERA5_FORCING", ERA5_LAND_DOCUMENTATION),
        "10m_u_component_of_wind": VariableDefinition("m s-1", "instantaneous", "INTERPOLATED_ERA5_FORCING", ERA5_LAND_DOCUMENTATION),
        "10m_v_component_of_wind": VariableDefinition("m s-1", "instantaneous", "INTERPOLATED_ERA5_FORCING", ERA5_LAND_DOCUMENTATION),
        "surface_pressure": VariableDefinition("Pa", "instantaneous", "INTERPOLATED_ERA5_FORCING", ERA5_LAND_DOCUMENTATION),
        "total_precipitation": VariableDefinition("m", "accumulation", "INTERPOLATED_ERA5_FORCING", ERA5_LAND_DOCUMENTATION),
        "total_runoff": VariableDefinition("m", "accumulation", "LAND_MODEL_OUTPUT", ERA5_LAND_DOCUMENTATION),
        "volumetric_soil_water_layer_1": VariableDefinition("m3 m-3", "instantaneous", "LAND_MODEL_OUTPUT", ERA5_LAND_DOCUMENTATION),
    },
}
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_TIME_PATTERN = re.compile(r"^(?:[01]\d|2[0-3]):00$")
_SECRET_KEY_MARKERS = ("password", "token", "secret", "authorization", "api_key", "credential")

LifecycleState = Literal[
    "REQUESTED",
    "SUBMITTED",
    "RETRIEVING",
    "DOWNLOADED",
    "VALIDATING",
    "VALIDATED",
    "UNAVAILABLE",
    "INCOMPLETE",
    "FAILED",
]
ReleaseStatus = Literal["ERA5T", "FINAL", "ERA5_LAND_T", "CONSOLIDATED", "UNKNOWN"]
OutputFormat = Literal["grib", "netcdf"]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class GeographicArea(ContractModel):
    west: float = Field(ge=-180, le=180, allow_inf_nan=False, strict=True)
    south: float = Field(ge=-90, le=90, allow_inf_nan=False, strict=True)
    east: float = Field(ge=-180, le=180, allow_inf_nan=False, strict=True)
    north: float = Field(ge=-90, le=90, allow_inf_nan=False, strict=True)

    @model_validator(mode="after")
    def validate_order(self) -> GeographicArea:
        if self.west >= self.east:
            raise ValueError(
                "Antimeridian-crossing or zero-width areas are not supported; "
                "split the request into west/east non-crossing areas."
            )
        if self.south >= self.north:
            raise ValueError("Area south must be less than north.")
        return self

    @property
    def area_square_degrees(self) -> float:
        return (self.east - self.west) * (self.north - self.south)


class ReanalysisRequest(ContractModel):
    product: Literal["ERA5", "ERA5-Land"]
    dataset_id: str
    variables: tuple[str, ...] = Field(min_length=1)
    start_date: date
    end_date: date
    times_utc: tuple[str, ...] = Field(min_length=1)
    area: GeographicArea
    output_format: OutputFormat

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def require_explicit_iso_date(cls, value: Any) -> date:
        if isinstance(value, datetime) or not isinstance(value, (date, str)):
            raise ValueError("Dates must be explicit ISO-8601 calendar dates (YYYY-MM-DD).")
        if isinstance(value, str):
            try:
                parsed = date.fromisoformat(value)
            except ValueError as error:
                raise ValueError("Dates must be explicit ISO-8601 calendar dates (YYYY-MM-DD).") from error
            if parsed.isoformat() != value:
                raise ValueError("Dates must use the exact YYYY-MM-DD format.")
            return parsed
        return value

    @field_validator("variables", mode="before")
    @classmethod
    def normalize_variables(cls, value: Any) -> tuple[str, ...]:
        if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
            raise ValueError("variables must be an explicit list of variable identifiers.")
        if not value:
            raise ValueError("variables must contain at least one allowlisted identifier.")
        if any(not isinstance(item, str) or not item for item in value):
            raise ValueError("Each variable identifier must be a non-empty string.")
        if len(set(value)) != len(value):
            raise ValueError("Duplicate variables are not allowed.")
        return tuple(sorted(value))

    @field_validator("times_utc", mode="before")
    @classmethod
    def normalize_times(cls, value: Any) -> tuple[str, ...]:
        if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
            raise ValueError("times_utc must be an explicit list of UTC hourly times.")
        if not value:
            raise ValueError("times_utc must contain at least one explicit UTC hour.")
        if any(not isinstance(item, str) or not _TIME_PATTERN.fullmatch(item) for item in value):
            raise ValueError("times_utc entries must be explicit hourly UTC times from 00:00 through 23:00.")
        if len(set(value)) != len(value):
            raise ValueError("Duplicate times are not allowed.")
        return tuple(sorted(value))

    @field_validator("output_format", mode="before")
    @classmethod
    def normalize_format(cls, value: Any) -> Any:
        return value.lower() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_product_dataset(self) -> ReanalysisRequest:
        expected = PRODUCT_DATASET_IDS[self.product]
        if self.dataset_id != expected:
            raise ValueError(f"{self.product} requires CDS dataset_id {expected!r}.")
        supported_variables = VARIABLE_METADATA[self.product]
        unsupported = sorted(set(self.variables) - set(supported_variables))
        if unsupported:
            raise ValueError(
                f"Unsupported {self.product} variable identifier(s): {', '.join(unsupported)}."
            )
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date.")
        if self.end_date > datetime.now(timezone.utc).date():
            raise ValueError("Future dates are not allowed for a historical reanalysis request.")
        return self


class RequestLimits(ContractModel):
    max_time_span_days: int = Field(default=1, ge=1, strict=True)
    max_area_square_degrees: float = Field(default=1.0, gt=0, allow_inf_nan=False, strict=True)
    max_variables: int = Field(default=2, ge=1, strict=True)


class VariableMetadata(ContractModel):
    product_identity: Literal["ERA5", "ERA5-Land"]
    variable_id: str
    native_unit: str
    temporal_kind: Literal["instantaneous", "mean", "accumulation", "unknown"]
    role: VariableRole
    role_evidence_reference: str = Field(min_length=1)
    temporal_bounds_description: str | None = None
    accumulation_semantics: str | None = None
    missing_value_description: str | None = None
    land_mask_description: str | None = None

    @field_validator("role_evidence_reference")
    @classmethod
    def require_role_evidence_reference(cls, value: str) -> str:
        if not value.startswith("https://"):
            raise ValueError("role_evidence_reference must be an HTTPS source reference.")
        return value


class CDSRequestCandidate(ContractModel):
    product_identity: Literal["ERA5", "ERA5-Land"]
    dataset_id: str
    serializer_id: Literal[
        "era5-single-levels-candidate-v1",
        "era5-land-candidate-v1",
    ]
    status: Literal["UNVERIFIED_CANDIDATE"] = "UNVERIFIED_CANDIDATE"
    executable: Literal[False] = False
    normalized_request: ReanalysisRequest
    candidate_payload: dict[str, Any]
    output_format_candidate: OutputFormat
    confirmation_required: tuple[str, ...]


class _CDSRequestAdapter:
    product: Literal["ERA5", "ERA5-Land"]
    serializer_id: Literal[
        "era5-single-levels-candidate-v1",
        "era5-land-candidate-v1",
    ]

    @classmethod
    def serialize(
        cls,
        request: ReanalysisRequest | Mapping[str, Any],
        limits: RequestLimits | None = None,
    ) -> CDSRequestCandidate:
        normalized = validate_reanalysis_request(request, limits)
        if normalized.product != cls.product:
            raise ValueError(
                f"{cls.__name__} cannot serialize product {normalized.product!r}."
            )
        if normalized.dataset_id != PRODUCT_DATASET_IDS[cls.product]:
            raise ValueError(f"{cls.__name__} received an inconsistent CDS dataset ID.")

        dates = tuple(
            normalized.start_date + timedelta(days=offset)
            for offset in range((normalized.end_date - normalized.start_date).days + 1)
        )
        return CDSRequestCandidate(
            product_identity=cls.product,
            dataset_id=normalized.dataset_id,
            serializer_id=cls.serializer_id,
            normalized_request=normalized,
            candidate_payload={
                "variable": list(normalized.variables),
                "year": sorted({value.strftime("%Y") for value in dates}),
                "month": sorted({value.strftime("%m") for value in dates}),
                "day": sorted({value.strftime("%d") for value in dates}),
                "time": list(normalized.times_utc),
                "area": [
                    normalized.area.north,
                    normalized.area.west,
                    normalized.area.south,
                    normalized.area.east,
                ],
            },
            output_format_candidate=normalized.output_format,
            confirmation_required=(
                "Current dataset-generated selector names and accepted values",
                "Date selector semantics for this exact date range",
                "Output format selector and availability for this dataset",
            ),
        )


class ERA5CDSRequestAdapter(_CDSRequestAdapter):
    product: Literal["ERA5"] = "ERA5"
    serializer_id: Literal["era5-single-levels-candidate-v1"] = (
        "era5-single-levels-candidate-v1"
    )


class ERA5LandCDSRequestAdapter(_CDSRequestAdapter):
    product: Literal["ERA5-Land"] = "ERA5-Land"
    serializer_id: Literal["era5-land-candidate-v1"] = "era5-land-candidate-v1"


class GridMetadata(ContractModel):
    coordinate_reference_system: Literal["OGC:CRS84"] = "OGC:CRS84"
    requested_area: GeographicArea
    latitude_coordinate_name: str | None = None
    longitude_coordinate_name: str | None = None
    valid_time_coordinate_name: str | None = None
    time_bounds_coordinate_name: str | None = None
    grid_spacing_degrees: tuple[float, float] | None = None
    actual_latitude_range: tuple[float, float] | None = None
    actual_longitude_range: tuple[float, float] | None = None
    land_mask_description: str | None = None

    @model_validator(mode="after")
    def validate_grid_ranges(self) -> GridMetadata:
        if self.grid_spacing_degrees is not None and any(value <= 0 for value in self.grid_spacing_degrees):
            raise ValueError("Grid spacing values must be positive.")
        for name, value, low, high in (
            ("latitude", self.actual_latitude_range, -90, 90),
            ("longitude", self.actual_longitude_range, -180, 180),
        ):
            if value is not None and (
                value[0] < low or value[1] > high or value[0] > value[1]
            ):
                raise ValueError(f"Actual {name} range is invalid.")
        return self


class SourceFile(ContractModel):
    file_name: str = Field(min_length=1)
    file_size_bytes: int = Field(gt=0)
    output_format: OutputFormat
    sha256: str

    @field_validator("file_name")
    @classmethod
    def require_safe_file_name(cls, value: str) -> str:
        if value in {".", ".."} or "/" in value or "\\" in value:
            raise ValueError("file_name must be a file name, not a path.")
        return value

    @field_validator("sha256")
    @classmethod
    def require_sha256(cls, value: str) -> str:
        if not _SHA256_PATTERN.fullmatch(value):
            raise ValueError("sha256 must be a lowercase 64-character hexadecimal digest.")
        return value


class ValidationCheck(ContractModel):
    name: str = Field(min_length=1)
    status: Literal["PASSED", "FAILED", "NOT_RUN"]
    details: str | None = None


class ValidationResults(ContractModel):
    status: Literal["NOT_RUN", "PASSED", "FAILED"] = "NOT_RUN"
    validator_version: str | None = None
    validated_at_utc: datetime | None = None
    checks: tuple[ValidationCheck, ...] = ()
    warnings: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_report(self) -> ValidationResults:
        if self.status == "PASSED" and (
            not self.validator_version
            or self.validated_at_utc is None
            or not self.checks
            or any(check.status != "PASSED" for check in self.checks)
        ):
            raise ValueError(
                "A passing validation report requires a version, timestamp, and all checks passing."
            )
        if self.status == "FAILED" and self.checks and not any(
            check.status == "FAILED" for check in self.checks
        ):
            raise ValueError("A failed validation report must include at least one failed check.")
        return self

    @field_validator("validated_at_utc")
    @classmethod
    def require_aware_validation_time(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("validated_at_utc must include a timezone.")
        return value.astimezone(timezone.utc) if value is not None else None


class ReanalysisExtractManifest(ContractModel):
    contract_version: Literal["1.1"] = CONTRACT_VERSION
    provider: Literal["ECMWF/Copernicus CDS"] = PROVIDER
    product: Literal["ERA5", "ERA5-Land"]
    dataset_id: str
    dataset_revision: str | None = None
    release_status: ReleaseStatus = "UNKNOWN"
    lifecycle_state: LifecycleState = "REQUESTED"
    request: ReanalysisRequest
    validation_limits: RequestLimits = Field(default_factory=RequestLimits)
    request_sha256: str
    requested_at_utc: datetime
    submitted_at_utc: datetime | None = None
    retrieved_at_utc: datetime | None = None
    provider_job_id: str | None = None
    source_terms_reference: str = Field(min_length=1)
    source_terms_status: Literal["UNVERIFIED", "ACCEPTED"] = "UNVERIFIED"
    grid: GridMetadata
    variables: tuple[VariableMetadata, ...] = Field(min_length=1)
    source_file: SourceFile | None = None
    validation: ValidationResults = Field(default_factory=ValidationResults)
    status_detail: str | None = None

    @field_validator("request_sha256")
    @classmethod
    def require_request_sha256(cls, value: str) -> str:
        if not _SHA256_PATTERN.fullmatch(value):
            raise ValueError("request_sha256 must be a lowercase 64-character hexadecimal digest.")
        return value

    @field_validator("requested_at_utc", "submitted_at_utc", "retrieved_at_utc")
    @classmethod
    def normalize_utc_timestamps(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("Manifest timestamps must include a timezone.")
        return value.astimezone(timezone.utc) if value is not None else None

    @model_validator(mode="after")
    def validate_manifest_consistency(self) -> ReanalysisExtractManifest:
        if self.product != self.request.product or self.dataset_id != self.request.dataset_id:
            raise ValueError("Manifest product and dataset_id must match its canonical request.")
        validate_reanalysis_request(self.request, self.validation_limits)
        if self.release_status not in PRODUCT_RELEASE_STATUSES[self.product]:
            raise ValueError(f"Invalid release_status for product {self.product!r}.")
        if self.request_sha256 != _request_identity_sha256(self.request):
            raise ValueError("request_sha256 does not match the canonical request.")
        if self.submitted_at_utc and self.submitted_at_utc < self.requested_at_utc:
            raise ValueError("submitted_at_utc cannot precede requested_at_utc.")
        if (
            self.retrieved_at_utc
            and self.submitted_at_utc
            and self.retrieved_at_utc < self.submitted_at_utc
        ):
            raise ValueError("retrieved_at_utc cannot precede submitted_at_utc.")
        if self.grid.requested_area != self.request.area:
            raise ValueError("grid.requested_area must match the request area.")
        variable_ids = tuple(item.variable_id for item in self.variables)
        if variable_ids != self.request.variables:
            raise ValueError("Manifest variable metadata must match the canonical request variables.")
        expected_metadata = VARIABLE_METADATA[self.product]
        for item in self.variables:
            if item.product_identity != self.product:
                raise ValueError(
                    f"Variable {item.variable_id!r} product_identity must match manifest product."
                )
            definition = expected_metadata[item.variable_id]
            if item.native_unit != definition.native_unit:
                raise ValueError(
                    f"Unsupported native unit {item.native_unit!r} for {item.variable_id!r}; "
                    f"expected {definition.native_unit!r}."
                )
            if item.temporal_kind not in {definition.temporal_kind, "unknown"}:
                raise ValueError(f"Invalid temporal_kind for {item.variable_id!r}.")
            if item.role not in {definition.role, "UNKNOWN"}:
                raise ValueError(
                    f"Invalid provenance role {item.role!r} for {self.product} "
                    f"variable {item.variable_id!r}; expected {definition.role!r} or 'UNKNOWN'."
                )
        if self.source_file is not None and self.source_file.output_format != self.request.output_format:
            raise ValueError("source_file output format must match the requested format.")
        if self.lifecycle_state in {"DOWNLOADED", "VALIDATING", "VALIDATED"}:
            if self.source_file is None or self.retrieved_at_utc is None:
                raise ValueError(
                    f"{self.lifecycle_state} requires source file metadata and retrieved_at_utc."
                )
        if self.lifecycle_state in {
            "SUBMITTED",
            "RETRIEVING",
            "DOWNLOADED",
            "VALIDATING",
            "VALIDATED",
        } and self.submitted_at_utc is None:
            raise ValueError(f"{self.lifecycle_state} requires submitted_at_utc.")
        if self.lifecycle_state != "REQUESTED" and self.lifecycle_state not in {
            "FAILED",
            "UNAVAILABLE",
        } and self.source_terms_status != "ACCEPTED":
            raise ValueError(f"{self.lifecycle_state} requires accepted dataset terms.")
        if self.lifecycle_state == "VALIDATED":
            self._require_successful_validation()
            if self.source_terms_status != "ACCEPTED":
                raise ValueError("VALIDATED requires documented acceptance of the dataset terms.")
            if (
                self.validation.validated_at_utc is not None
                and self.retrieved_at_utc is not None
                and self.validation.validated_at_utc < self.retrieved_at_utc
            ):
                raise ValueError("validated_at_utc cannot precede retrieved_at_utc.")
            unresolved = [
                item.variable_id
                for item in self.variables
                if item.temporal_kind == "unknown"
                or not item.missing_value_description
                or (
                    item.temporal_kind == "accumulation"
                    and (
                        not item.temporal_bounds_description
                        or not item.accumulation_semantics
                        or not self.grid.time_bounds_coordinate_name
                    )
                )
            ]
            if unresolved:
                raise ValueError(
                    "VALIDATED requires resolved temporal and missing-value metadata for: "
                    + ", ".join(unresolved)
                    + "."
                )
            if (
                self.grid.latitude_coordinate_name is None
                or self.grid.longitude_coordinate_name is None
                or self.grid.valid_time_coordinate_name is None
                or self.grid.grid_spacing_degrees is None
            ):
                raise ValueError("VALIDATED requires verified grid and valid-time coordinate metadata.")
            if self.product == "ERA5-Land" and not self.grid.land_mask_description:
                raise ValueError("VALIDATED ERA5-Land metadata must describe its land/ocean mask.")
        if self.lifecycle_state in {"UNAVAILABLE", "INCOMPLETE", "FAILED"} and not self.status_detail:
            raise ValueError(f"{self.lifecycle_state} requires status_detail.")
        return self

    def _require_successful_validation(self) -> None:
        if (
            self.validation.status != "PASSED"
            or not self.validation.validator_version
            or self.validation.validated_at_utc is None
            or not self.validation.checks
            or any(check.status != "PASSED" for check in self.validation.checks)
        ):
            raise ValueError(
                "VALIDATED requires a passing validation report, validator version, timestamp, "
                "and all checks passing."
            )


_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "REQUESTED": frozenset({"SUBMITTED", "UNAVAILABLE", "FAILED"}),
    "SUBMITTED": frozenset({"RETRIEVING", "UNAVAILABLE", "FAILED"}),
    "RETRIEVING": frozenset({"DOWNLOADED", "INCOMPLETE", "FAILED", "UNAVAILABLE"}),
    "DOWNLOADED": frozenset({"VALIDATING", "INCOMPLETE", "FAILED"}),
    "VALIDATING": frozenset({"VALIDATED", "INCOMPLETE", "FAILED"}),
    "VALIDATED": frozenset(),
    "UNAVAILABLE": frozenset(),
    "INCOMPLETE": frozenset(),
    "FAILED": frozenset(),
}


def _reject_secret_keys(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key).casefold()
            if any(marker in key_text for marker in _SECRET_KEY_MARKERS):
                raise ValueError(f"Secret-like field {key!r} is not allowed in reanalysis requests or manifests.")
            _reject_secret_keys(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _reject_secret_keys(child)


def validate_reanalysis_request(
    request: ReanalysisRequest | Mapping[str, Any],
    limits: RequestLimits | None = None,
) -> ReanalysisRequest:
    _reject_secret_keys(request.model_dump(mode="json") if isinstance(request, ReanalysisRequest) else request)
    validated = ReanalysisRequest.model_validate(
        request.model_dump(mode="json") if isinstance(request, ReanalysisRequest) else request
    )
    bounds = limits or RequestLimits()
    duration_days = (validated.end_date - validated.start_date).days + 1
    if duration_days > bounds.max_time_span_days:
        raise ValueError(
            f"Request spans {duration_days} days; the configured maximum is "
            f"{bounds.max_time_span_days} day(s)."
        )
    if validated.area.area_square_degrees > bounds.max_area_square_degrees:
        raise ValueError(
            f"Request area is {validated.area.area_square_degrees:g} square degrees; "
            f"the configured maximum is {bounds.max_area_square_degrees:g}."
        )
    if len(validated.variables) > bounds.max_variables:
        raise ValueError(
            f"Request has {len(validated.variables)} variables; "
            f"the configured maximum is {bounds.max_variables}."
        )
    return validated


def canonical_request_json(
    request: ReanalysisRequest | Mapping[str, Any],
    limits: RequestLimits | None = None,
) -> str:
    validated = validate_reanalysis_request(request, limits)
    return _serialize_request(validated)


def _serialize_request(request: ReanalysisRequest) -> str:
    return json.dumps(
        request.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def _request_identity_sha256(request: ReanalysisRequest) -> str:
    return hashlib.sha256(_serialize_request(request).encode("utf-8")).hexdigest()


def request_sha256(
    request: ReanalysisRequest | Mapping[str, Any],
    limits: RequestLimits | None = None,
) -> str:
    validated = validate_reanalysis_request(request, limits)
    return _request_identity_sha256(validated)


def create_extract_manifest(
    request: ReanalysisRequest | Mapping[str, Any],
    *,
    requested_at_utc: datetime,
    source_terms_reference: str,
    source_terms_status: Literal["UNVERIFIED", "ACCEPTED"] = "UNVERIFIED",
    limits: RequestLimits | None = None,
) -> ReanalysisExtractManifest:
    validated = validate_reanalysis_request(request, limits)
    metadata = VARIABLE_METADATA[validated.product]
    return ReanalysisExtractManifest(
        product=validated.product,
        dataset_id=validated.dataset_id,
        request=validated,
        validation_limits=limits or RequestLimits(),
        request_sha256=request_sha256(validated, limits),
        requested_at_utc=requested_at_utc,
        source_terms_reference=source_terms_reference,
        source_terms_status=source_terms_status,
        grid=GridMetadata(requested_area=validated.area),
        variables=tuple(
            VariableMetadata(
                product_identity=validated.product,
                variable_id=variable,
                native_unit=metadata[variable].native_unit,
                temporal_kind=metadata[variable].temporal_kind,
                role=metadata[variable].role,
                role_evidence_reference=metadata[variable].role_evidence_reference,
            )
            for variable in validated.variables
        ),
    )


def validate_manifest(manifest: ReanalysisExtractManifest | Mapping[str, Any]) -> ReanalysisExtractManifest:
    _reject_secret_keys(manifest.model_dump(mode="json") if isinstance(manifest, ReanalysisExtractManifest) else manifest)
    return ReanalysisExtractManifest.model_validate(
        manifest.model_dump(mode="json") if isinstance(manifest, ReanalysisExtractManifest) else manifest
    )


def serialize_manifest(manifest: ReanalysisExtractManifest | Mapping[str, Any]) -> str:
    validated = validate_manifest(manifest)
    return json.dumps(
        validated.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def transition_manifest(
    manifest: ReanalysisExtractManifest | Mapping[str, Any],
    next_state: LifecycleState,
    *,
    status_detail: str | None = None,
    updates: Mapping[str, Any] | None = None,
) -> ReanalysisExtractManifest:
    current = validate_manifest(manifest)
    if next_state not in _ALLOWED_TRANSITIONS[current.lifecycle_state]:
        raise ValueError(
            f"Invalid lifecycle transition: {current.lifecycle_state} -> {next_state}."
        )
    allowed_updates = {
        "submitted_at_utc",
        "retrieved_at_utc",
        "provider_job_id",
        "source_file",
        "validation",
        "grid",
        "variables",
    }
    if updates and set(updates) - allowed_updates:
        raise ValueError(
            "Lifecycle updates may only provide submitted/retrieved times, source_file, "
            "validation, grid, or variable metadata."
        )
    changes: dict[str, Any] = {
        "lifecycle_state": next_state,
        "status_detail": status_detail,
        **(updates or {}),
    }
    if next_state in {"UNAVAILABLE", "INCOMPLETE", "FAILED"} and not status_detail:
        raise ValueError(f"{next_state} transition requires status_detail.")
    if next_state == "VALIDATED":
        changes["status_detail"] = None
    updated = current.model_dump(mode="json")
    updated.update(changes)
    return validate_manifest(updated)
