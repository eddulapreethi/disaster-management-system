from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models.hydrological_observation import HydrologicalObservation
from app.models.weather_observation import WeatherObservation
from app.schemas.environmental_data import (
    EnvironmentalDataRecord,
    EnvironmentalDataResponse,
    EnvironmentalDataSourceStatus,
)
from app.services.environmental_normalization_service import (
    normalize_hydrology_record,
    normalize_weather_record,
)
from app.services.hydrology_service import configured_resources, get_stale_after_hours
from app.services.weather_service import get_max_age_seconds

CATEGORIES = {
    "weather_observation",
    "hydrological_observation",
    "disaster_event_report",
    "weather_forecast",
    "satellite_scene_metadata",
    "geographic_reference_dataset",
}
WEATHER_UNITS = {
    "temperature_c": "°C",
    "humidity_percent": "%",
    "precipitation_mm": "mm",
    "rain_mm": "mm",
    "wind_speed_kmh": "km/h",
    "pressure_hpa": "hPa",
}
HYDROLOGY_FIELDS = ("water_level", "discharge", "rainfall")
HYDROLOGY_UNITS = {"water_level": "m", "rainfall": "mm"}


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _storage_time(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return _utc(value).replace(tzinfo=None)


def _valid_coordinates(latitude: float | None, longitude: float | None) -> bool:
    return (
        latitude is not None
        and longitude is not None
        and math.isfinite(latitude)
        and math.isfinite(longitude)
        and -90 <= latitude <= 90
        and -180 <= longitude <= 180
    )


def _within_radius(latitude: float | None, longitude: float | None, center: tuple[float, float, float] | None) -> bool:
    if center is None:
        return True
    if not _valid_coordinates(latitude, longitude):
        return False
    center_lat, center_lon, radius_km = center
    lat1, lat2 = math.radians(center_lat), math.radians(latitude)
    delta_lat = lat2 - lat1
    delta_lon = math.radians(longitude - center_lon)
    haversine = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    )
    distance_km = 6371.0088 * 2 * math.asin(math.sqrt(min(1.0, haversine)))
    return distance_km <= radius_km


def _inside_bbox(latitude: float | None, longitude: float | None, bbox: tuple[float, float, float, float] | None) -> bool:
    if bbox is None:
        return True
    if not _valid_coordinates(latitude, longitude):
        return False
    west, south, east, north = bbox
    longitude_inside = west <= longitude <= east if west <= east else longitude >= west or longitude <= east
    return south <= latitude <= north and longitude_inside


def _freshness(observation_time: datetime, max_age_seconds: int, now: datetime) -> str:
    age = (now - _utc(observation_time)).total_seconds()
    if age < -300:
        return "ERROR"
    return "STALE" if age > max_age_seconds else "READY"


def _validate_measurements(
    values: dict[str, float | None],
    *,
    minimums: dict[str, float] | None = None,
    maximums: dict[str, float] | None = None,
) -> list[str]:
    findings = []
    for name, value in values.items():
        if value is None:
            continue
        if not math.isfinite(value):
            findings.append(f"{name} is non-finite; the stored source value is preserved.")
        elif minimums and name in minimums and value < minimums[name]:
            findings.append(f"{name} is below its valid range; the stored source value is preserved.")
        elif maximums and name in maximums and value > maximums[name]:
            findings.append(f"{name} is above its valid range; the stored source value is preserved.")
    return findings


def _json_safe_values(values: dict[str, float | None]) -> dict[str, float | str | None]:
    result: dict[str, float | str | None] = {}
    for name, value in values.items():
        if value is not None and not math.isfinite(value):
            result[name] = "NaN" if math.isnan(value) else "Infinity" if value > 0 else "-Infinity"
        else:
            result[name] = value
    return result


def _json_safe(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return "NaN" if math.isnan(value) else "Infinity" if value > 0 else "-Infinity"
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def _weather_record(row: WeatherObservation, now: datetime) -> dict[str, Any]:
    values = {name: getattr(row, name) for name in WEATHER_UNITS}
    findings: list[str] = []
    if not _valid_coordinates(row.latitude, row.longitude):
        findings.append("Stored coordinates are missing or outside WGS 84 ranges.")
    if any(value is None for value in (row.temperature_c, row.precipitation_mm, row.wind_speed_kmh)):
        findings.append("One or more required weather measurements are missing; missing values remain null.")
    measurement_findings = _validate_measurements(
        values,
        minimums={"humidity_percent": 0, "precipitation_mm": 0, "rain_mm": 0, "wind_speed_kmh": 0, "pressure_hpa": 0},
        maximums={"humidity_percent": 100},
    )
    findings.extend(measurement_findings)
    freshness = _freshness(row.observation_time, get_max_age_seconds(), now)
    if freshness == "ERROR":
        findings.append("Observation timestamp is more than five minutes in the future.")
    if freshness == "STALE":
        findings.append("Observation is older than the configured weather freshness window.")
    if not row.provider_metadata:
        findings.append("Provider-specific metadata was not retained for this record.")
    provider_metadata = row.provider_metadata if isinstance(row.provider_metadata, dict) else {}
    if row.provider_metadata is not None and not isinstance(row.provider_metadata, dict):
        findings.append("Stored provider metadata is malformed; the raw value is retained.")
    raw_source_values = (
        {"provider_source": row.source, **provider_metadata}
        if isinstance(row.provider_metadata, dict)
        else {"provider_source": row.source, "provider_metadata_raw": row.provider_metadata}
    )
    if provider_metadata.get("timezone") is None:
        findings.append("Original provider timezone metadata is unavailable.")
    quality = (
        "INVALID"
        if not _valid_coordinates(row.latitude, row.longitude) or measurement_findings
        else "PARTIAL"
        if any(value is None for value in (row.temperature_c, row.precipitation_mm, row.wind_speed_kmh))
        else "VALIDATED_SHAPE"
    )
    return {
        "category": "weather_observation",
        "record_id": row.id,
        "provider": "Open-Meteo",
        "source_record_id": None,
        "measurement_category": "weather",
        "latitude": row.latitude,
        "longitude": row.longitude,
        "geographic_metadata": {
            "name": row.station_name,
            "station_id": row.station_id,
            "station_id_is_internal": True,
            "coordinate_reference_system": "OGC:CRS84",
        },
        "observation_time": row.observation_time,
        "event_time": None,
        "event_timezone": provider_metadata.get("timezone"),
        "fetched_at": row.fetched_at,
        "ingested_at": row.created_at,
        "reported_at": None,
        "values": _json_safe_values(values),
        "units": WEATHER_UNITS,
        "raw_source_values": _json_safe(raw_source_values),
        "quality_status": quality,
        "freshness_status": freshness,
        "validation_findings": findings,
        "attribution": "Open-Meteo; source attribution and licensing terms apply.",
        "license_metadata": "CC BY 4.0 data attribution; deployment usage terms depend on API plan.",
    }


def _hydrology_record(row: HydrologicalObservation, now: datetime) -> dict[str, Any]:
    values = {name: getattr(row, name) for name in HYDROLOGY_FIELDS}
    findings: list[str] = []
    if not _valid_coordinates(row.latitude, row.longitude):
        findings.append("Source station coordinates are missing or outside WGS 84 ranges.")
    if all(value is None for value in values.values()):
        findings.append("No hydrological measurement is present; values remain null.")
    measurement_findings = _validate_measurements(values, minimums={"water_level": 0, "discharge": 0, "rainfall": 0})
    findings.extend(measurement_findings)
    resource = next(
        (item for item in configured_resources() if item["resource_id"] == row.source_resource_id),
        None,
    )
    freshness = _freshness(
        row.observation_time,
        get_stale_after_hours(resource) * 3600,
        now,
    )
    if freshness == "ERROR":
        findings.append("Observation timestamp is more than five minutes in the future.")
    if freshness == "STALE":
        findings.append("Observation is older than the configured resource freshness window.")
    findings.append("Station identifier, timezone, datum, and measurement metadata require source verification.")
    metadata = row.provider_metadata if isinstance(row.provider_metadata, dict) else {}
    if row.provider_metadata is not None and not isinstance(row.provider_metadata, dict):
        findings.append("Stored provider metadata is malformed; the raw value is retained.")
    raw_source_values = (
        {"source_resource_id": row.source_resource_id, **metadata}
        if isinstance(row.provider_metadata, dict)
        else {"source_resource_id": row.source_resource_id, "provider_metadata_raw": row.provider_metadata}
    )
    raw_timestamp = metadata.get("source_timestamp_raw")
    return {
        "category": "hydrological_observation",
        "record_id": row.id,
        "provider": "NWDP/NWIC CWC",
        "source_record_id": row.source_record_id,
        "measurement_category": "hydrology",
        "hazard": "flood",
        "latitude": row.latitude,
        "longitude": row.longitude,
        "geographic_metadata": {
            "name": row.station_name,
            "station_id": row.station_id,
            "source_resource_id": row.source_resource_id,
            "station_id_is_internal": True,
            "river": row.river_name,
            "state": row.state_name,
            "district": row.district_name,
            "coordinate_reference_system": "OGC:CRS84",
        },
        "observation_time": row.observation_time,
        "event_time": None,
        "event_timezone": metadata.get("source_timezone"),
        "fetched_at": row.fetched_at,
        "ingested_at": None,
        "reported_at": None,
        "values": _json_safe_values(values),
        "units": HYDROLOGY_UNITS,
        "raw_source_values": _json_safe(raw_source_values),
        "quality_status": "INVALID" if not _valid_coordinates(row.latitude, row.longitude) or measurement_findings else (
            "PARTIAL" if all(value is None for value in values.values()) else "UNVERIFIED"
        ),
        "freshness_status": freshness,
        "validation_findings": findings + (
            ["Original provider timestamp is unavailable."] if raw_timestamp is None else []
        ),
        "attribution": "NWDP/NWIC CWC; source attribution and licensing terms apply.",
        "license_metadata": None,
    }


def _mark_duplicates(records: list[dict[str, Any]]) -> None:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for record in records:
        if record["category"] == "weather_observation":
            metadata = record["geographic_metadata"]
            key = (
                record["category"],
                record["provider"],
                metadata.get("source_resource_id"),
                metadata.get("station_id"),
                record["raw_source_values"].get("provider_source"),
                record["observation_time"],
            )
        elif record["category"] == "hydrological_observation":
            metadata = record["geographic_metadata"]
            key = (
                record["category"],
                record["provider"],
                metadata.get("source_resource_id"),
                metadata.get("station_id"),
                record["observation_time"],
            )
        else:
            continue
        groups.setdefault(key, []).append(record)

    for group in groups.values():
        if len(group) < 2:
            continue
        values = {json.dumps(record["values"], sort_keys=True, default=str) for record in group}
        for record in group:
            record["duplicate_key"] = True
            if len(values) > 1:
                record["conflicting_values"] = True
                record["validation_findings"].append(
                    "Records share a provider/station/time identity but contain conflicting values; originals are preserved."
                )


def _time_filter(record: dict[str, Any], start_time: datetime | None, end_time: datetime | None) -> bool:
    when = record["observation_time"]
    if when is None:
        return False
    normalized = _utc(when)
    return not (
        (start_time is not None and normalized < _utc(start_time))
        or (end_time is not None and normalized > _utc(end_time))
    )


def _provider_applies(provider: str | None, category_name: str) -> bool:
    if provider is None:
        return True
    requested = provider.casefold()
    aliases = {
        "weather_observation": {"open-meteo", "open-meteo forecast api"},
        "hydrological_observation": {"nwdp/nwic cwc", "nwdp", "cwc"},
        "disaster_event_report": {"disasterguard application report", "disasterguard"},
    }
    return requested in aliases[category_name]


def _select_rows(
    db: Session,
    model: Any,
    *,
    category_name: str,
    provider: str | None,
    bbox: tuple[float, float, float, float] | None,
    location: tuple[float, float, float] | None,
    start_time: datetime | None,
    end_time: datetime | None,
    limit: int,
) -> list[Any]:
    if not _provider_applies(provider, category_name):
        return []
    query = select(model)
    if category_name == "weather_observation":
        time_column = model.observation_time
        latitude_column, longitude_column = model.latitude, model.longitude
        order_columns = (model.observation_time.desc(), model.id.desc())
    else:
        time_column = model.observation_time
        latitude_column, longitude_column = model.latitude, model.longitude
        order_columns = (model.observation_time.desc(), model.id.desc())

    if start_time is not None:
        query = query.where(time_column >= _storage_time(start_time))
    if end_time is not None:
        query = query.where(time_column <= _storage_time(end_time))
    if bbox is not None:
        west, south, east, north = bbox
        longitude_filter = (
            and_(longitude_column >= west, longitude_column <= east)
            if west <= east
            else or_(longitude_column >= west, longitude_column <= east)
        )
        query = query.where(
            latitude_column >= south,
            latitude_column <= north,
            longitude_filter,
        )
    if location is not None:
        center_latitude, center_longitude, radius_km = location
        latitude_delta = radius_km / 110.574
        query = query.where(
            latitude_column >= max(-90, center_latitude - latitude_delta),
            latitude_column <= min(90, center_latitude + latitude_delta),
        )
        cosine = abs(math.cos(math.radians(center_latitude)))
        if cosine > 1e-8:
            longitude_delta = min(180, radius_km / (111.32 * cosine))
            west = center_longitude - longitude_delta
            east = center_longitude + longitude_delta
            if west < -180:
                longitude_filter = or_(longitude_column >= west + 360, longitude_column <= east)
            elif east > 180:
                longitude_filter = or_(longitude_column >= west, longitude_column <= east - 360)
            else:
                longitude_filter = and_(longitude_column >= west, longitude_column <= east)
            query = query.where(longitude_filter)
    ordered_query = query.order_by(*order_columns)
    if location is None:
        return db.scalars(ordered_query.limit(limit)).all()

    matching_rows: list[Any] = []
    scanned = 0
    batch_size = 500
    maximum_candidates = 50000
    while len(matching_rows) < limit and scanned < maximum_candidates:
        batch = db.scalars(
            ordered_query.limit(min(batch_size, maximum_candidates - scanned)).offset(scanned)
        ).all()
        if not batch:
            break
        scanned += len(batch)
        matching_rows.extend(
            row for row in batch
            if _within_radius(row.latitude, row.longitude, location)
        )
        if len(batch) < batch_size:
            break
    has_unscanned_candidates = (
        scanned == maximum_candidates
        and len(matching_rows) < limit
        and db.scalars(ordered_query.limit(1).offset(scanned)).first() is not None
    )
    if has_unscanned_candidates:
        raise ValueError(
            "The radius query exceeds the safe candidate scan limit; narrow the radius or time range."
        )
    return matching_rows[:limit]


def query_environmental_data(
    db: Session,
    *,
    category: str | None = None,
    provider: str | None = None,
    bbox: tuple[float, float, float, float] | None = None,
    location: tuple[float, float, float] | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    limit: int = 100,
    offset: int = 0,
) -> EnvironmentalDataResponse:
    if category is not None and category not in CATEGORIES:
        raise ValueError(f"category must be one of: {', '.join(sorted(CATEGORIES))}.")
    if bbox is not None:
        west, south, east, north = bbox
        if not all(math.isfinite(value) for value in bbox):
            raise ValueError("Bounding box values must be finite.")
        if not (-180 <= west <= 180 and -180 <= east <= 180 and -90 <= south < north <= 90):
            raise ValueError("Bounding box coordinates are outside WGS 84 limits.")
    if location is not None:
        latitude, longitude, radius = location
        if not _valid_coordinates(latitude, longitude) or not math.isfinite(radius) or not 0 < radius <= 500:
            raise ValueError("Location requires valid WGS 84 coordinates and a radius from 0 to 500 km.")
    if start_time and start_time.tzinfo is None or end_time and end_time.tzinfo is None:
        raise ValueError("Time filters must include a timezone.")
    if start_time and end_time and _utc(start_time) > _utc(end_time):
        raise ValueError("start_time must be before or equal to end_time.")
    if not 1 <= limit <= 1000:
        raise ValueError("limit must be between 1 and 1000.")
    if not 0 <= offset <= 10000:
        raise ValueError("offset must be between 0 and 10000.")

    now = datetime.now(timezone.utc)
    candidate_limit = limit + offset + 1
    weather_rows = _select_rows(
        db, WeatherObservation, category_name="weather_observation", provider=provider,
        bbox=bbox, location=location, start_time=start_time, end_time=end_time,
        limit=candidate_limit,
    ) if category in {None, "weather_observation"} else []
    hydro_rows = _select_rows(
        db, HydrologicalObservation, category_name="hydrological_observation", provider=provider,
        bbox=bbox, location=location, start_time=start_time, end_time=end_time,
        limit=candidate_limit,
    ) if category in {None, "hydrological_observation"} else []
    all_records = (
        [_weather_record(row, now) for row in weather_rows]
        + [_hydrology_record(row, now) for row in hydro_rows]
    )
    filtered = []
    for record in all_records:
        if category and record["category"] != category:
            continue
        if provider and not _provider_applies(provider, record["category"]):
            continue
        if not _inside_bbox(record["latitude"], record["longitude"], bbox):
            continue
        if not _within_radius(record["latitude"], record["longitude"], location):
            continue
        if (start_time or end_time) and not _time_filter(record, start_time, end_time):
            continue
        filtered.append(record)

    _mark_duplicates(filtered)
    filtered.sort(
        key=lambda item: _utc(
            item["observation_time"] or item["reported_at"] or item["ingested_at"] or item["fetched_at"]
        ),
        reverse=True,
    )
    page_records = filtered[offset:offset + limit]
    has_more = len(filtered) > offset + limit
    for record in page_records:
        if record["category"] == "weather_observation":
            record["canonical_record"] = normalize_weather_record(record)
        elif record["category"] == "hydrological_observation":
            record["canonical_record"] = normalize_hydrology_record(record)
    records = [EnvironmentalDataRecord.model_validate(item) for item in page_records]

    counts = {name: sum(item["category"] == name for item in page_records) for name in CATEGORIES}

    def available_status(category_name: str) -> str:
        category_records = [item for item in page_records if item["category"] == category_name]
        if not category_records:
            return "NO_MATCHING_STORED_RECORDS"
        freshness = [item["freshness_status"] for item in category_records]
        if all(status == "STALE" for status in freshness):
            return "STALE"
        if all(status == "ERROR" for status in freshness):
            return "ERROR"
        if all(status == "UNVERIFIED" for status in freshness):
            return "UNVERIFIED"
        if len(set(freshness)) > 1:
            return "PARTIAL"
        if all(status == "READY" for status in freshness) and all(
            item["quality_status"] == "UNVERIFIED" for item in category_records
        ):
            return "UNVERIFIED"
        if (
            all(status == "READY" for status in freshness)
            and all(item["quality_status"] == "VALIDATED_SHAPE" for item in category_records)
        ):
            return "AVAILABLE"
        if any(status in {"READY", "STALE", "ERROR"} for status in freshness):
            return "PARTIAL"
        return "UNVERIFIED"

    def observation_source_details(category_name: str) -> str:
        count = counts[category_name]
        status = available_status(category_name)
        if category_name == "weather_observation":
            source_description = "Stored model-derived weather records only; not local station observations."
            empty_description = (
                "No matching stored weather observations were returned on this page; provider coverage was not checked."
            )
        else:
            source_description = (
                "Configured regional hydrology records only; station identity and measurement metadata remain unverified."
            )
            empty_description = (
                "No matching stored hydrological observations were returned on this page; no substitute source is used."
            )
        if count == 0:
            return empty_description
        status_description = {
            "AVAILABLE": "Returned records pass the configured shape and freshness checks only.",
            "PARTIAL": "The returned page contains partial, stale, invalid, or mixed-quality records.",
            "STALE": "The returned records are stale under the configured source freshness policy.",
            "ERROR": "Returned record timestamps are invalid or too far in the future; this is not a provider request error.",
            "UNVERIFIED": "Returned record provenance or measurement metadata remains unverified.",
        }[status]
        return (
            f"{source_description} Status describes this returned page only; {status_description} "
            "No provider-wide coverage check was performed."
        )

    sources = [
        EnvironmentalDataSourceStatus(
            category="weather_observation",
            provider="Open-Meteo",
            status=available_status("weather_observation"),
            details=observation_source_details("weather_observation"),
            matching_records=counts["weather_observation"],
        ),
        EnvironmentalDataSourceStatus(
            category="weather_forecast",
            provider="Open-Meteo",
            status="NOT_PERSISTED",
            details="On-demand point weather is a separate workflow; no forecast records are stored in this catalog.",
            matching_records=0,
        ),
        EnvironmentalDataSourceStatus(
            category="hydrological_observation",
            provider="NWDP/NWIC CWC",
            status=available_status("hydrological_observation"),
            details=observation_source_details("hydrological_observation"),
            matching_records=counts["hydrological_observation"],
        ),
        EnvironmentalDataSourceStatus(
            category="disaster_event_report",
            provider="DisasterGuard application report",
            status="UNVERIFIED",
            details="Application report ownership and visibility are not modeled; report details are withheld from this catalog. No external event provider is integrated.",
            matching_records=0,
        ),
        EnvironmentalDataSourceStatus(
            category="satellite_scene_metadata",
            provider="Copernicus Data Space",
            status="NOT_PERSISTED",
            details="Catalog metadata requires a separate request-time search; neither Catalog results nor imagery are stored in this catalog.",
            matching_records=0,
        ),
        EnvironmentalDataSourceStatus(
            category="geographic_reference_dataset",
            provider="Local GIS",
            status="REGIONAL",
            details="Only configured Kochi reference layers are available; this record query does not search GIS files or imply global terrain coverage.",
            matching_records=0,
        ),
    ]
    return EnvironmentalDataResponse(
        checked_at=now,
        records=records,
        sources=sources,
        filters={
            "category": category,
            "provider": provider,
            "bbox": list(bbox) if bbox else None,
            "location": (
                {"latitude": location[0], "longitude": location[1], "radius_km": location[2]}
                if location
                else None
            ),
            "start_time": start_time.isoformat() if start_time else None,
            "end_time": end_time.isoformat() if end_time else None,
            "time_filter_semantics": "Observation time for stored measurements.",
            "limit": limit,
            "offset": offset,
        },
        pagination={
            "limit": limit,
            "offset": offset,
            "returned_records": len(records),
        },
        has_more=has_more,
    )
