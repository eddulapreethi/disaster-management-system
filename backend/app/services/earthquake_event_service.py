from __future__ import annotations

import math
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

from app.schemas.canonical_environmental import (
    CanonicalEnvironmentalRecord,
    CanonicalGeography,
    CanonicalSource,
    CanonicalTimestamps,
    HistoricalEventPayload,
    WGS84BoundingBox,
    WGS84Point,
)
from app.schemas.earthquake_events import (
    EarthquakeEventQueryFilters,
    EarthquakeEventQueryResponse,
)
from app.services.usgs_comcat_client import UsgsComcatClient, UsgsComcatResponseError

MAX_QUERY_DAYS = 30
MAX_LONGITUDE_SPAN_DEGREES = 30
MAX_LATITUDE_SPAN_DEGREES = 20
MAX_RESULTS = 500
_EVENT_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
_SOURCE_METADATA_FIELDS = (
    "net",
    "code",
    "ids",
    "sources",
    "types",
    "status",
    "place",
    "magType",
    "nst",
    "dmin",
    "rms",
    "gap",
    "alert",
    "sig",
)


def _utc_datetime(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone offset.")
    return value.astimezone(timezone.utc)


def _finite_number(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"USGS {field_name} must be numeric.")
    try:
        number = float(value)
    except (OverflowError, ValueError) as error:
        raise ValueError(f"USGS {field_name} must be finite.") from error
    if not math.isfinite(number):
        raise ValueError(f"USGS {field_name} must be finite.")
    return number


def _epoch_milliseconds(value: Any, field_name: str) -> datetime:
    timestamp = _finite_number(value, field_name) / 1000
    try:
        return datetime.fromtimestamp(timestamp, timezone.utc)
    except (OverflowError, OSError, ValueError) as error:
        raise ValueError(f"USGS {field_name} is outside the supported time range.") from error


def _event_url(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "earthquake.usgs.gov"
        or parsed.port not in (None, 443)
        or parsed.username is not None
        or parsed.password is not None
    ):
        return None
    return value[:2048]


def _small_metadata(properties: dict[str, Any]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key in _SOURCE_METADATA_FIELDS:
        value = properties.get(key)
        if isinstance(value, (str, int, float, bool)) or value is None:
            if isinstance(value, float) and not math.isfinite(value):
                continue
            result[key] = value
        elif isinstance(value, list) and len(value) <= 100 and all(
            isinstance(item, str) and len(item) <= 256 for item in value
        ):
            result[key] = value
    return result


def _record_from_feature(
    feature: dict[str, Any],
    *,
    retrieved_at: datetime,
    bbox: WGS84BoundingBox,
    start_time: datetime,
    end_time: datetime,
) -> CanonicalEnvironmentalRecord:
    properties = feature.get("properties")
    geometry = feature.get("geometry")
    if not isinstance(properties, dict) or not isinstance(geometry, dict):
        raise ValueError("USGS GeoJSON feature properties or geometry were invalid.")

    event_id = properties.get("id")
    feature_id = feature.get("id")
    if event_id is not None and feature_id is not None and event_id != feature_id:
        raise ValueError("USGS feature and property event IDs did not match.")
    if event_id is None:
        event_id = feature_id
    if not isinstance(event_id, str) or not _EVENT_ID_PATTERN.fullmatch(event_id):
        raise ValueError("USGS event ID was missing or invalid.")

    coordinates = geometry.get("coordinates")
    if geometry.get("type") != "Point" or not isinstance(coordinates, list) or len(coordinates) not in (2, 3):
        raise ValueError("USGS event geometry must be a GeoJSON Point.")
    longitude = _finite_number(coordinates[0], "longitude")
    latitude = _finite_number(coordinates[1], "latitude")
    if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
        raise ValueError("USGS event coordinates were outside WGS84 bounds.")
    longitude_is_inside = (
        bbox.west <= longitude <= bbox.east
        if bbox.west <= bbox.east
        else longitude >= bbox.west or longitude <= bbox.east
    )
    if not longitude_is_inside or not bbox.south <= latitude <= bbox.north:
        raise ValueError("USGS event coordinates were outside the requested bounding box.")
    depth_km = _finite_number(coordinates[2], "depth") if len(coordinates) == 3 else None

    event_time = _epoch_milliseconds(properties.get("time"), "event time")
    if not start_time <= event_time <= end_time:
        raise ValueError("USGS event time was outside the requested time range.")

    source_updated_time = None
    if properties.get("updated") is not None:
        source_updated_time = _epoch_milliseconds(properties["updated"], "update time")

    magnitude = properties.get("mag")
    if magnitude is not None:
        magnitude = _finite_number(magnitude, "magnitude")
        if not -10 <= magnitude <= 10:
            raise ValueError("USGS magnitude was outside the supported range.")
    magnitude_type = properties.get("magType")
    if magnitude_type is not None and (
        not isinstance(magnitude_type, str) or not magnitude_type.strip() or len(magnitude_type) > 40
    ):
        raise ValueError("USGS magnitude type was invalid.")

    status = properties.get("status")
    if status is not None and (not isinstance(status, str) or len(status) > 64):
        raise ValueError("USGS review status was invalid.")
    network = properties.get("net")
    if network is not None and (not isinstance(network, str) or len(network) > 32):
        raise ValueError("USGS network metadata was invalid.")
    code = properties.get("code")
    if code is not None and (not isinstance(code, str) or len(code) > 100):
        raise ValueError("USGS source code metadata was invalid.")

    source_metadata = _small_metadata(properties)
    source_metadata["source_scope"] = "USGS ComCat"
    source_metadata["source_event_time_format"] = "Unix epoch milliseconds"
    if source_updated_time is not None:
        source_metadata["source_updated_at_utc"] = (
            source_updated_time.isoformat().replace("+00:00", "Z")
        )

    event_attributes: dict[str, object] = {
        "provider_event_id": event_id,
        "review_status": status,
        "network": network,
        "source_code": code,
        "depth_km": depth_km,
        "magnitude": magnitude,
        "magnitude_type": magnitude_type,
    }
    if source_updated_time is not None:
        event_attributes["source_updated_at_utc"] = (
            source_updated_time.isoformat().replace("+00:00", "Z")
        )

    return CanonicalEnvironmentalRecord(
        record_type="historical_event",
        hazard_type="earthquake",
        source=CanonicalSource(
            provider="USGS ComCat",
            source_record_id=event_id,
            source_dataset_id="USGS ComCat",
            source_url=_event_url(properties.get("url")),
            attribution="U.S. Geological Survey (USGS) ComCat",
            license_usage_status="UNKNOWN",
            license_usage_details=(
                "Contributor and product redistribution terms have not been verified."
            ),
            source_metadata=source_metadata,
        ),
        timestamps=CanonicalTimestamps(
            source_timestamp_raw=str(properties["time"]),
            source_timezone="UTC",
            event_time_utc=event_time,
            retrieval_time_utc=retrieved_at,
        ),
        geography=CanonicalGeography(
            source_coordinates=WGS84Point(latitude=latitude, longitude=longitude),
            coverage_scope="POINT",
            coverage_verified=True,
            coverage_limitations=[
                "Catalog completeness and event impact are not verified by DisasterGuard."
            ],
        ),
        quality_status="UNVERIFIED",
        freshness_status="NOT_CHECKED",
        availability_status="AVAILABLE",
        payload=HistoricalEventPayload(
            event_name=properties.get("title") if isinstance(properties.get("title"), str) else None,
            event_description=(
                properties.get("place") if isinstance(properties.get("place"), str) else None
            ),
            event_attributes=event_attributes,
        ),
    )


def _revision_time(record: CanonicalEnvironmentalRecord) -> datetime:
    value = record.source.source_metadata.get("source_updated_at_utc")
    if not isinstance(value, str):
        return datetime.min.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _split_longitude_bounds(bbox: WGS84BoundingBox) -> list[tuple[float, float]]:
    if bbox.west > bbox.east:
        return [(bbox.west, 180.0), (-180.0, bbox.east)]
    return [(bbox.west, bbox.east)]


def query_earthquake_events(
    *,
    west: float,
    south: float,
    east: float,
    north: float,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    min_magnitude: float | None = None,
    max_magnitude: float | None = None,
    review_status: str | None = None,
    limit: int = 100,
    client: UsgsComcatClient | None = None,
    now: datetime | None = None,
) -> EarthquakeEventQueryResponse:
    bbox = WGS84BoundingBox(west=west, south=south, east=east, north=north)
    now_utc = _utc_datetime(now or datetime.now(timezone.utc), "now")
    normalized_end = _utc_datetime(end_time, "end_time") if end_time is not None else now_utc
    normalized_start = (
        _utc_datetime(start_time, "start_time")
        if start_time is not None
        else normalized_end - timedelta(days=7)
    )

    longitude_span = (bbox.east - bbox.west) % 360
    if longitude_span <= 0:
        raise ValueError("Bounding-box longitude span must be greater than zero.")
    latitude_span = bbox.north - bbox.south
    if longitude_span > MAX_LONGITUDE_SPAN_DEGREES:
        raise ValueError(f"Bounding-box longitude span must not exceed {MAX_LONGITUDE_SPAN_DEGREES} degrees.")
    if latitude_span > MAX_LATITUDE_SPAN_DEGREES:
        raise ValueError(f"Bounding-box latitude span must not exceed {MAX_LATITUDE_SPAN_DEGREES} degrees.")
    if normalized_start > normalized_end:
        raise ValueError("start_time must not be after end_time.")
    if normalized_end > now_utc:
        raise ValueError("end_time must not be in the future.")
    if normalized_end - normalized_start > timedelta(days=MAX_QUERY_DAYS):
        raise ValueError(f"Time range must not exceed {MAX_QUERY_DAYS} days.")
    if min_magnitude is not None and max_magnitude is not None and min_magnitude > max_magnitude:
        raise ValueError("min_magnitude must not exceed max_magnitude.")
    for magnitude in (min_magnitude, max_magnitude):
        if magnitude is not None and (
            not math.isfinite(magnitude) or not -10 <= magnitude <= 10
        ):
            raise ValueError("Magnitude filters must be finite values between -10 and 10.")
    if not 1 <= limit <= MAX_RESULTS:
        raise ValueError(f"limit must be between 1 and {MAX_RESULTS}.")
    if review_status not in (None, "automatic", "reviewed"):
        raise ValueError("review_status must be 'automatic' or 'reviewed'.")

    owns_client = client is None
    provider_client = client if client is not None else UsgsComcatClient()
    try:
        features_to_normalize: list[dict[str, Any]] = []
        for west_bound, east_bound in _split_longitude_bounds(bbox):
            features_to_normalize.extend(
                provider_client.query(
                    start_time=normalized_start,
                    end_time=normalized_end,
                    west=west_bound,
                    south=bbox.south,
                    east=east_bound,
                    north=bbox.north,
                    min_magnitude=min_magnitude,
                    max_magnitude=max_magnitude,
                    review_status=review_status,
                    limit=limit,
                )
            )
    finally:
        if owns_client:
            provider_client.close()

    retrieved_at = datetime.now(timezone.utc)
    records_by_id: dict[str, CanonicalEnvironmentalRecord] = {}
    for feature in features_to_normalize:
        try:
            record = _record_from_feature(
                feature,
                retrieved_at=retrieved_at,
                bbox=bbox,
                start_time=normalized_start,
                end_time=normalized_end,
            )
        except ValueError as error:
            raise UsgsComcatResponseError(
                "The USGS GeoJSON contained an invalid earthquake event."
            ) from error
        event_id = str(record.source.source_record_id)
        previous = records_by_id.get(event_id)
        if previous is None or _revision_time(record) > _revision_time(previous):
            records_by_id[event_id] = record

    records = sorted(
        records_by_id.values(),
        key=lambda item: item.timestamps.event_time_utc or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )[:limit]
    filters = EarthquakeEventQueryFilters(
        bbox=bbox,
        start_time=normalized_start,
        end_time=normalized_end,
        min_magnitude=min_magnitude,
        max_magnitude=max_magnitude,
        review_status=review_status,
        limit=limit,
    )
    return EarthquakeEventQueryResponse(
        retrieved_at=retrieved_at,
        data_status="AVAILABLE" if records else "NO_MATCHING_EVENTS",
        filters=filters,
        returned_events=len(records),
        records=records,
    )
