from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.schemas.canonical_environmental import (
    CanonicalEnvironmentalRecord,
    CanonicalGeography,
    CanonicalMeasurement,
    CanonicalSource,
    CanonicalTimestamps,
    ObservationPayload,
    SatelliteAcquisitionPayload,
    WGS84BoundingBox,
    WGS84Point,
)

_UNIT_BASES: dict[str, tuple[str, float, float]] = {
    "°C": ("temperature", 1.0, 0.0),
    "C": ("temperature", 1.0, 0.0),
    "°F": ("temperature", 5 / 9, -32 * 5 / 9),
    "F": ("temperature", 5 / 9, -32 * 5 / 9),
    "K": ("temperature", 1.0, -273.15),
    "%": ("fraction_percent", 1.0, 0.0),
    "mm": ("length_m", 0.001, 0.0),
    "m": ("length_m", 1.0, 0.0),
    "m/s": ("speed_kmh", 3.6, 0.0),
    "km/h": ("speed_kmh", 1.0, 0.0),
    "hPa": ("pressure_hpa", 1.0, 0.0),
}

_WEATHER_FIELDS = {
    "temperature_c": ("temperature_2m", "°C"),
    "humidity_percent": ("relative_humidity_2m", "%"),
    "precipitation_mm": ("precipitation", "mm"),
    "rain_mm": ("rain", "mm"),
    "wind_speed_kmh": ("wind_speed_10m", "km/h"),
    "pressure_hpa": ("surface_pressure", "hPa"),
}
_HYDROLOGY_FIELDS = {
    "water_level": ("River Water Level Telemetry Hourly (meter)", "m"),
    "discharge": (None, None),
    "rainfall": ("Telemetry Hourly Rainfall (mm)", "mm"),
}
@dataclass(frozen=True)
class NormalizedTimestamp:
    source_timestamp_raw: str
    source_timezone: str | None
    timezone_assumption: str | None
    utc: datetime


def _finite_value(value: Any) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError("Measurement value must be numeric.") from error
    if not math.isfinite(numeric):
        raise ValueError("Measurement value must be finite.")
    return numeric


def normalize_measurement(
    value: Any,
    source_unit: str | None,
    normalized_unit: str,
) -> tuple[float | None, str]:
    """Convert only units with an explicitly known dimension and affine transform."""
    if not isinstance(source_unit, str) or source_unit not in _UNIT_BASES:
        raise ValueError(f"Unknown or ambiguous source unit: {source_unit!r}.")
    if normalized_unit not in _UNIT_BASES:
        raise ValueError(f"Unknown normalized unit: {normalized_unit!r}.")
    source_dimension, source_factor, source_offset = _UNIT_BASES[source_unit]
    target_dimension, target_factor, target_offset = _UNIT_BASES[normalized_unit]
    if source_dimension != target_dimension:
        raise ValueError("Source and normalized units have incompatible dimensions.")
    if value is None:
        return None, "unit_validated_value_missing"
    numeric = _finite_value(value)
    base_value = numeric * source_factor + source_offset
    result = (base_value - target_offset) / target_factor
    if not math.isfinite(result):
        raise ValueError("Normalized measurement is non-finite.")
    transformation = (
        "validated_no_unit_conversion"
        if source_unit == normalized_unit
        else f"converted_{source_unit}_to_{normalized_unit}"
    )
    return result, transformation


def normalize_source_timestamp(
    value: str | datetime,
    *,
    source_timezone: str | None = None,
    timezone_assumption: str | None = None,
) -> NormalizedTimestamp:
    """Normalize a timestamp only when its offset or timezone interpretation is known."""
    if isinstance(value, datetime):
        parsed = value
        raw = value.isoformat()
    elif isinstance(value, str) and value.strip():
        raw = value
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("Source timestamp is not a supported ISO-8601 value.") from error
    else:
        raise ValueError("Source timestamp is missing.")

    assumption = None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        timezone_name = source_timezone or timezone_assumption
        if not timezone_name:
            raise ValueError("Naive source timestamp has no timezone or documented assumption.")
        try:
            zone = ZoneInfo(timezone_name)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError("Source timestamp timezone is not a valid IANA timezone.") from error
        first = parsed.replace(tzinfo=zone, fold=0)
        second = parsed.replace(tzinfo=zone, fold=1)
        first_round_trip = first.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None)
        second_round_trip = second.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None)
        if first_round_trip != parsed or second_round_trip != parsed:
            raise ValueError("Naive source timestamp falls in a nonexistent local-time interval.")
        if first.utcoffset() != second.utcoffset():
            raise ValueError("Ambiguous local source timestamp needs an explicit UTC offset.")
        parsed = first
        assumption = timezone_assumption or f"interpreted using source timezone {timezone_name}"
        source_timezone = source_timezone or timezone_name
    elif source_timezone is not None:
        try:
            zone = ZoneInfo(source_timezone)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError("Source timestamp timezone is not a valid IANA timezone.") from error
        if parsed.astimezone(zone).utcoffset() != parsed.utcoffset():
            raise ValueError("Source timestamp offset conflicts with its declared timezone.")

    return NormalizedTimestamp(
        source_timestamp_raw=raw,
        source_timezone=source_timezone or (parsed.tzname() if parsed.tzinfo else None),
        timezone_assumption=assumption,
        utc=parsed.astimezone(timezone.utc),
    )


def _stored_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _point(latitude: Any, longitude: Any) -> WGS84Point | None:
    if latitude is None or longitude is None:
        return None
    try:
        latitude_value = _finite_value(latitude)
        longitude_value = _finite_value(longitude)
        if not (-90 <= latitude_value <= 90 and -180 <= longitude_value <= 180):
            return None
        return WGS84Point(latitude=latitude_value, longitude=longitude_value)
    except ValueError:
        return None


def _json_safe(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return "NaN" if math.isnan(value) else "Infinity" if value > 0 else "-Infinity"
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _safe_source_metadata(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _safe_source_metadata(item)
            for key, item in value.items()
            if not any(
                marker in str(key).casefold()
                for marker in ("access_token", "authorization", "client_secret", "api_key")
            )
        }
    if isinstance(value, (list, tuple)):
        return [_safe_source_metadata(item) for item in value]
    return _json_safe(value)


def _bbox(values: Any) -> WGS84BoundingBox | None:
    if values is None:
        return None
    if isinstance(values, Mapping):
        return WGS84BoundingBox(
            west=values["west"],
            south=values["south"],
            east=values["east"],
            north=values["north"],
        )
    west, south, east, north = values
    return WGS84BoundingBox(west=west, south=south, east=east, north=north)


def _source_value(value: Any) -> float | str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return str(value)
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not math.isfinite(numeric):
        return "NaN" if math.isnan(numeric) else "Infinity" if numeric > 0 else "-Infinity"
    return numeric


def _quality(
    existing: str | None,
    freshness: str,
    findings: list[str],
) -> str:
    if existing == "INVALID":
        return "INVALID"
    if freshness == "STALE":
        return "STALE"
    if any("invalid" in item.lower() or "non-finite" in item.lower() for item in findings):
        return "INVALID"
    if findings:
        return "INCOMPLETE_METADATA"
    return "UNVERIFIED"


def _freshness(value: str | None) -> str:
    return {
        "READY": "FRESH",
        "STALE": "STALE",
        "ERROR": "UNAVAILABLE",
        "UNAVAILABLE": "UNAVAILABLE",
        "UNVERIFIED": "NOT_CHECKED",
    }.get(value or "", "NOT_CHECKED")


def normalize_weather_record(record: Mapping[str, Any]) -> CanonicalEnvironmentalRecord:
    provider_metadata = record.get("provider_metadata")
    if not isinstance(provider_metadata, Mapping):
        raw_source_values = record.get("raw_source_values")
        if isinstance(raw_source_values, Mapping):
            nested_metadata = raw_source_values.get("source_metadata")
            provider_metadata = (
                nested_metadata
                if isinstance(nested_metadata, Mapping)
                else {
                    key: value
                    for key, value in raw_source_values.items()
                    if key not in {"provider_source", "provider_metadata_raw"}
                }
            )
        else:
            provider_metadata = {}
    else:
        provider_metadata = dict(provider_metadata)

    raw_current = provider_metadata.get("source_current")
    raw_current = raw_current if isinstance(raw_current, Mapping) else {}
    source_units = provider_metadata.get("current_units")
    source_units = source_units if isinstance(source_units, Mapping) else {}
    stored_values = record.get("values")
    stored_values = stored_values if isinstance(stored_values, Mapping) else record
    findings = list(record.get("validation_findings") or [])
    measurements: list[CanonicalMeasurement] = []

    for name, (source_field, expected_unit) in _WEATHER_FIELDS.items():
        source_value = raw_current.get(source_field) if source_field in raw_current else stored_values.get(name)
        source_unit = (
            source_units.get(source_field)
            if source_field in raw_current
            else expected_unit
        )
        try:
            normalized_value, transformation = normalize_measurement(
                source_value,
                source_unit,
                expected_unit,
            )
        except ValueError as error:
            normalized_value = None
            transformation = None
            findings.append(f"{name}: {error}")
        measurements.append(
            CanonicalMeasurement(
                name=name,
                source_value=_source_value(source_value),
                source_unit=source_unit,
                normalized_value=normalized_value,
                normalized_unit=expected_unit if transformation is not None else None,
                transformation=transformation,
            )
        )

    raw_time = provider_metadata.get("source_timestamp_raw")
    source_timezone = provider_metadata.get("source_timezone") or provider_metadata.get("timezone")
    timezone_assumption = provider_metadata.get("timezone_assumption")
    observation_time = _stored_utc(record.get("observation_time"))
    if not raw_time:
        findings.append("Original provider timestamp text was not retained for this stored record.")
    if not source_timezone and not timezone_assumption:
        findings.append("Provider timezone metadata is unavailable.")
    if raw_current and not source_units:
        findings.append("Original provider units are unavailable for the preserved current values.")

    quality = _quality(
        record.get("quality_status"),
        record.get("freshness_status", "UNVERIFIED"),
        findings,
    )
    source_id = record.get("source_record_id")
    if source_id is None:
        findings.append("Provider did not expose a source record identifier for this point record.")
        if quality not in {"INVALID", "STALE"}:
            quality = "INCOMPLETE_METADATA"

    requested = _point(
        record.get("requested_latitude", record.get("latitude")),
        record.get("requested_longitude", record.get("longitude")),
    )
    provider_latitude = record.get("provider_latitude", provider_metadata.get("latitude"))
    provider_longitude = record.get("provider_longitude", provider_metadata.get("longitude"))
    if requested is None:
        findings.append("Requested WGS 84 coordinates are missing or invalid.")
    if _point(provider_latitude, provider_longitude) is None:
        findings.append("Provider-returned WGS 84 coordinates are missing or invalid.")

    return CanonicalEnvironmentalRecord(
        local_record_id=record.get("record_id", record.get("id")),
        record_type="observation",
        hazard_type=None,
        source=CanonicalSource(
            provider=str(record.get("provider") or "Open-Meteo"),
            source_record_id=source_id,
            source_dataset_id="open-meteo-current-weather",
            source_url="https://api.open-meteo.com/v1/forecast",
            attribution="Open-Meteo; source attribution and licensing terms apply.",
            license_usage_status="UNVERIFIED",
            license_usage_details="Intended-use eligibility must be checked against the active API plan and terms.",
            transformation_metadata={
                "unit_policy": "Only known source units are converted; source and normalized values are retained separately.",
                "time_policy": "Stored source timestamps are normalized to UTC; retrieval time remains separate.",
                "observation_semantics": "Provider current fields are model-derived, not in-situ station measurements.",
            },
            source_metadata={
                key: _safe_source_metadata(value)
                for key, value in provider_metadata.items()
                if key not in {"source_current", "access_token", "authorization"}
            },
        ),
        timestamps=CanonicalTimestamps(
            source_timestamp_raw=str(raw_time) if raw_time is not None else None,
            source_timezone=str(source_timezone) if source_timezone is not None else None,
            timezone_assumption=(
                str(timezone_assumption) if timezone_assumption is not None else None
            ),
            observation_time_utc=observation_time,
            retrieval_time_utc=_stored_utc(record.get("fetched_at")),
            ingestion_time_utc=_stored_utc(record.get("ingested_at", record.get("created_at"))),
        ),
        geography=CanonicalGeography(
            requested_coordinates=requested,
            provider_returned_coordinates=_point(provider_latitude, provider_longitude),
            station_id=record.get("station_id")
            or (record.get("geographic_metadata") or {}).get("station_id"),
            station_id_is_internal=True,
            station_name=record.get("station_name")
            or (record.get("geographic_metadata") or {}).get("name"),
            coverage_scope="POINT",
            coverage_verified=False,
            coverage_limitations=[
                "A successful coordinate-based response does not establish worldwide variable coverage.",
                "The provider-returned model grid point is not a local station identity.",
            ],
        ),
        quality_status=quality,
        freshness_status=_freshness(record.get("freshness_status")),
        availability_status=(
            "STALE"
            if record.get("freshness_status") == "STALE"
            else "ERROR"
            if record.get("freshness_status") == "ERROR"
            else "UNVERIFIED"
        ),
        validation_errors=list(dict.fromkeys(findings)),
        payload=ObservationPayload(
            measurement_basis="model_derived",
            measurements=measurements,
        ),
    )


def normalize_hydrology_record(record: Mapping[str, Any]) -> CanonicalEnvironmentalRecord:
    metadata = record.get("provider_metadata")
    if not isinstance(metadata, Mapping):
        raw_source_values = record.get("raw_source_values")
        metadata = (
            raw_source_values
            if isinstance(raw_source_values, Mapping)
            else {}
        )
    source_record = metadata.get("source_record")
    source_record = source_record if isinstance(source_record, Mapping) else {}
    findings = list(record.get("validation_findings") or [])
    measurements: list[CanonicalMeasurement] = []
    stored_values = record.get("values")
    stored_values = stored_values if isinstance(stored_values, Mapping) else record
    source_column = metadata.get("source_value_column")
    for name, (default_column, expected_unit) in _HYDROLOGY_FIELDS.items():
        value = stored_values.get(name)
        if value is None:
            continue
        column = source_column if name == "water_level" or name == "rainfall" else default_column
        source_value = source_record.get(column) if column and column in source_record else value
        source_unit = expected_unit if column and column == default_column else None
        if source_unit is None:
            findings.append(f"{name}: original source unit is unavailable; normalized value is not inferred.")
            normalized_value = None
            transformation = None
        else:
            try:
                normalized_value, transformation = normalize_measurement(
                    source_value,
                    source_unit,
                    expected_unit,
                )
            except ValueError as error:
                normalized_value = None
                transformation = None
                findings.append(f"{name}: {error}")
        measurements.append(
            CanonicalMeasurement(
                name=name,
                source_value=_source_value(source_value),
                source_unit=source_unit,
                normalized_value=normalized_value,
                normalized_unit=expected_unit if transformation is not None else None,
                transformation=transformation,
            )
        )

    raw_timestamp = metadata.get("source_timestamp_raw")
    source_timezone = metadata.get("source_timezone")
    timezone_assumption = metadata.get("source_timezone_assumption")
    if not raw_timestamp:
        findings.append("Original provider timestamp text was not retained.")
    if not source_timezone and not timezone_assumption:
        findings.append("Timezone for the stored source timestamp is not known.")
    findings.append("Station identifier and vertical datum are not verified by the stored source metadata.")
    source_id = record.get("source_record_id")
    if _point(record.get("latitude"), record.get("longitude")) is None:
        findings.append("Source station WGS 84 coordinates are missing or invalid.")

    return CanonicalEnvironmentalRecord(
        local_record_id=record.get("record_id", record.get("id")),
        record_type="observation",
        hazard_type="flood",
        source=CanonicalSource(
            provider=str(record.get("provider") or "NWDP/NWIC CWC"),
            source_record_id=source_id,
            source_dataset_id=str(
                record.get("source_resource_id")
                or (record.get("geographic_metadata") or {}).get("source_resource_id")
                or ""
            )
            or None,
            attribution="NWDP/NWIC CWC; source attribution and licensing terms apply.",
            license_usage_status="UNKNOWN",
            license_usage_details="The applicable redistribution and operational-use terms have not been established.",
            transformation_metadata={
                "unit_policy": "Only the configured source value-column units are normalized; no datum conversion is applied.",
                "time_policy": "Stored observation time is UTC. Legacy rows may not retain the timezone assumption used at ingestion.",
                "station_policy": "Generated station keys are internal and are not official provider station identifiers.",
            },
            source_metadata=_safe_source_metadata(metadata),
        ),
        timestamps=CanonicalTimestamps(
            source_timestamp_raw=str(raw_timestamp) if raw_timestamp is not None else None,
            source_timezone=str(source_timezone) if source_timezone is not None else None,
            timezone_assumption=(
                str(timezone_assumption) if timezone_assumption is not None else None
            ),
            observation_time_utc=_stored_utc(record.get("observation_time")),
            retrieval_time_utc=_stored_utc(record.get("fetched_at")),
        ),
        geography=CanonicalGeography(
            source_coordinates=_point(record.get("latitude"), record.get("longitude")),
            station_id=record.get("station_id")
            or (record.get("geographic_metadata") or {}).get("station_id"),
            station_id_is_internal=True,
            station_name=record.get("station_name")
            or (record.get("geographic_metadata") or {}).get("name"),
            coverage_scope="REGIONAL",
            coverage_verified=False,
            coverage_limitations=[
                "Configured CWC resources are regional and do not establish national or worldwide station coverage.",
                "No verified station-to-location or vertical-datum mapping is available.",
            ],
        ),
        quality_status=_quality(
            record.get("quality_status"),
            record.get("freshness_status", "UNVERIFIED"),
            findings,
        ),
        freshness_status=_freshness(record.get("freshness_status")),
        availability_status=(
            "STALE" if record.get("freshness_status") == "STALE" else "REGIONAL"
        ),
        validation_errors=list(dict.fromkeys(findings)),
        payload=ObservationPayload(
            measurement_basis="station_telemetry",
            measurements=measurements,
        ),
    )


def normalize_satellite_acquisition(
    *,
    provider: str,
    collection: str | None,
    catalog_item_id: str | None,
    acquisition_time: datetime | None,
    retrieved_at: datetime | None,
    requested_bbox: Any = None,
    source_bbox: Any = None,
    requested_point: Any = None,
    bands: list[str] | None = None,
    output_format: str | None = None,
    output_units: str | None = None,
    process_result_pinned_to_catalog_item: bool | None = None,
    source_metadata: Mapping[str, Any] | None = None,
) -> CanonicalEnvironmentalRecord:
    limitations = ["Catalog metadata and imagery availability were not live-verified."]
    if process_result_pinned_to_catalog_item is False:
        limitations.append("Process API output is matched by AOI and time, not pinned to the Catalog item.")
    return CanonicalEnvironmentalRecord(
        record_type="satellite_acquisition",
        hazard_type=None,
        source=CanonicalSource(
            provider=provider,
            source_record_id=catalog_item_id,
            source_dataset_id=collection,
            license_usage_status="UNVERIFIED",
            license_usage_details="Provider terms and intended-use eligibility require separate verification.",
            transformation_metadata={
                "acquisition_policy": "Catalog acquisition time and image retrieval time are distinct.",
            },
            source_metadata=dict(source_metadata or {}),
        ),
        timestamps=CanonicalTimestamps(
            acquisition_time_utc=_stored_utc(acquisition_time),
            retrieval_time_utc=_stored_utc(retrieved_at),
        ),
        geography=CanonicalGeography(
            requested_coordinates=(
                _point(requested_point.get("latitude"), requested_point.get("longitude"))
                if isinstance(requested_point, Mapping)
                else None
            ),
            requested_bbox=_bbox(requested_bbox),
            source_bbox=_bbox(source_bbox),
            coverage_scope="UNKNOWN",
            coverage_verified=False,
            coverage_limitations=limitations,
        ),
        quality_status="UNVERIFIED",
        freshness_status="NOT_CHECKED",
        availability_status="UNVERIFIED",
        validation_errors=[
            "Imagery is not a confirmed hazard detection.",
            *(
                ["Process output is not demonstrably pinned to this Catalog item."]
                if process_result_pinned_to_catalog_item is False
                else []
            ),
        ],
        payload=SatelliteAcquisitionPayload(
            collection=collection,
            catalog_item_id=catalog_item_id,
            bands=bands or [],
            output_format=output_format,
            output_units=output_units,
            process_result_pinned_to_catalog_item=process_result_pinned_to_catalog_item,
        ),
    )
