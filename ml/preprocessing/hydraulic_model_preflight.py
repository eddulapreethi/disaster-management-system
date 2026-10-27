from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import sys
from typing import Any
from urllib.parse import urlsplit


REQUIRED_INPUTS = (
    "terrain",
    "channel_geometry",
    "gauge_metadata",
    "water_level_observations",
    "official_danger_levels",
    "rainfall_forcing",
    "initial_conditions",
    "upstream_boundary_conditions",
    "downstream_boundary_conditions",
    "calibration_observations",
    "validation_observations",
)
VERTICAL_INPUTS = {
    "terrain",
    "channel_geometry",
    "gauge_metadata",
    "water_level_observations",
    "official_danger_levels",
}
TIME_SERIES_INPUTS = {
    "water_level_observations",
    "rainfall_forcing",
    "upstream_boundary_conditions",
    "downstream_boundary_conditions",
    "calibration_observations",
    "validation_observations",
}
REVIEW_AXES = (
    "source_authenticity",
    "licensing",
    "domain_approval",
    "scientific_suitability",
)
_UNKNOWN = {"", "UNKNOWN", "UNVERIFIED", "TBD", "N/A", "NONE", "NULL"}
_EPSG_PATTERN = re.compile(r"^EPSG:\d+$", re.IGNORECASE)
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE)
_ALLOWED_UNITS = {
    "m", "meter", "meters", "metre", "metres", "ft", "foot", "feet",
    "mm", "millimeter", "millimeters", "millimetre", "millimetres",
    "cm", "in", "inch", "inches", "mm/h", "mm/hr", "mm/hour", "mm/day",
    "m/h", "m/hr", "m/hour", "m3/s", "m^3/s", "cumec", "cumecs",
    "ft3/s", "ft^3/s", "cfs", "m/s", "km/h", "degree", "degrees",
    "dimensionless", "s", "sec", "second", "seconds", "min", "minute",
    "minutes", "h", "hr", "hour", "hours",
}
_GEOSPATIAL_INPUTS = {"terrain", "channel_geometry", "gauge_metadata"}
_VERTICAL_UNIT_KEYS = {
    "terrain": ("vertical", "elevation"),
    "channel_geometry": ("vertical", "elevation"),
    "gauge_metadata": ("vertical", "water_level"),
    "water_level_observations": ("vertical", "water_level"),
    "official_danger_levels": ("vertical", "water_level"),
}
_UNIT_ALIASES = {
    "meter": "m",
    "meters": "m",
    "metre": "m",
    "metres": "m",
    "foot": "ft",
    "feet": "ft",
    "inch": "in",
    "inches": "in",
    "millimeter": "mm",
    "millimeters": "mm",
    "millimetre": "mm",
    "millimetres": "mm",
    "mm/hr": "mm/hour",
    "mm/h": "mm/hour",
    "m/hr": "m/hour",
    "m/h": "m/hour",
    "m^3/s": "m3/s",
    "cumec": "m3/s",
    "cumecs": "m3/s",
    "ft^3/s": "ft3/s",
    "cfs": "ft3/s",
}


def _canonical_unit(value: Any) -> str:
    normalized = str(value).strip().casefold()
    return _UNIT_ALIASES.get(normalized, normalized)


def _is_missing(value: Any) -> bool:
    return value is None or (
        isinstance(value, str) and value.strip().upper() in _UNKNOWN
    )


def _timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is missing.")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{field} must be a valid ISO-8601 timestamp.") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must include an explicit timezone offset.")
    return parsed.astimezone(timezone.utc)


def _bounds(
    value: Any,
    field: str,
    *,
    allow_point_extent: bool = False,
) -> tuple[float, float, float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise ValueError(f"{field} must be [west, south, east, north] in WGS 84.")
    try:
        west, south, east, north = (float(item) for item in value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must contain four finite numbers.") from error
    if not all(math.isfinite(item) for item in (west, south, east, north)):
        raise ValueError(f"{field} must contain four finite numbers.")
    valid_longitude = west <= east if allow_point_extent else west < east
    valid_latitude = south <= north if allow_point_extent else south < north
    if not (
        -180 <= west <= 180
        and -90 <= south <= 90
        and -180 <= east <= 180
        and -90 <= north <= 90
        and valid_longitude
        and valid_latitude
    ):
        raise ValueError(f"{field} has invalid WGS 84 bounds.")
    return west, south, east, north


def _intersects(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> bool:
    return (
        first[0] <= second[2]
        and first[2] >= second[0]
        and first[1] <= second[3]
        and first[3] >= second[1]
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _geojson_bounds(payload: Any) -> tuple[float, float, float, float]:
    if (
        not isinstance(payload, dict)
        or payload.get("type") != "FeatureCollection"
        or not isinstance(payload.get("features"), list)
        or not payload["features"]
    ):
        raise ValueError("Expected a non-empty GeoJSON FeatureCollection.")
    points: list[tuple[float, float]] = []

    def visit(value: Any) -> None:
        if not isinstance(value, list):
            return
        if (
            len(value) >= 2
            and isinstance(value[0], (int, float))
            and not isinstance(value[0], bool)
            and isinstance(value[1], (int, float))
            and not isinstance(value[1], bool)
        ):
            longitude, latitude = float(value[0]), float(value[1])
            if (
                not math.isfinite(longitude)
                or not math.isfinite(latitude)
                or not -180 <= longitude <= 180
                or not -90 <= latitude <= 90
            ):
                raise ValueError("GeoJSON contains invalid WGS 84 coordinates.")
            points.append((longitude, latitude))
            return
        for item in value:
            visit(item)

    for feature in payload["features"]:
        geometry = feature.get("geometry") if isinstance(feature, dict) else None
        if not isinstance(geometry, dict) or geometry.get("type") not in {
            "Point",
            "MultiPoint",
            "LineString",
            "MultiLineString",
            "Polygon",
            "MultiPolygon",
            "GeometryCollection",
        }:
            raise ValueError("GeoJSON feature is missing a geometry.")
        if geometry.get("type") == "GeometryCollection":
            geometries = geometry.get("geometries")
            if not isinstance(geometries, list):
                raise ValueError("GeoJSON GeometryCollection is malformed.")
            for member in geometries:
                if not isinstance(member, dict):
                    raise ValueError("GeoJSON GeometryCollection member is malformed.")
                visit(member.get("coordinates"))
        else:
            visit(geometry.get("coordinates"))
    if not points:
        raise ValueError("GeoJSON contains no coordinate pairs.")
    longitudes, latitudes = zip(*points)
    return min(longitudes), min(latitudes), max(longitudes), max(latitudes)


def _validate_tiff(path: Path, require_geotags: bool) -> None:
    file_size = path.stat().st_size
    with path.open("rb") as stream:
        header = stream.read(8)
        if len(header) != 8 or header[:2] not in {b"II", b"MM"}:
            raise ValueError("File does not have a valid TIFF header.")
        byte_order = "<" if header[:2] == b"II" else ">"
        magic, ifd_offset = struct.unpack(f"{byte_order}HI", header[2:])
        if magic != 42:
            raise ValueError("Only classic TIFF is supported by this preflight.")
        if ifd_offset < 8 or ifd_offset + 2 > file_size:
            raise ValueError("TIFF first image directory is outside the file.")
        stream.seek(ifd_offset)
        count_bytes = stream.read(2)
        if len(count_bytes) != 2:
            raise ValueError("TIFF image directory is truncated.")
        entry_count = struct.unpack(f"{byte_order}H", count_bytes)[0]
        entries_end = ifd_offset + 2 + entry_count * 12 + 4
        if entries_end > file_size:
            raise ValueError("TIFF image directory is truncated.")
        tags: dict[int, tuple[int, int, int]] = {}
        for _ in range(entry_count):
            entry = stream.read(12)
            tag, field_type, count, value = struct.unpack(
                f"{byte_order}HHII", entry
            )
            tags[tag] = (field_type, count, value)
        if 256 not in tags or 257 not in tags:
            raise ValueError("TIFF is missing image width or height.")
        for tag in (256, 257):
            field_type, count, value = tags[tag]
            if count != 1 or field_type not in {3, 4} or value <= 0:
                raise ValueError("TIFF image dimensions are invalid.")
        if require_geotags and not {33550, 33922, 34735}.issubset(tags):
            raise ValueError("GeoTIFF is missing scale, tiepoint, or GeoKey metadata.")


def _file_status(
    name: str,
    descriptor: Any,
    root: Path,
    study_bounds: tuple[float, float, float, float] | None,
    model_horizontal_crs: str | None,
    model_vertical_datum: str | None,
    model_vertical_unit: str | None,
    model_rainfall_unit: str | None,
) -> dict[str, Any]:
    errors: list[str] = []
    missing: list[str] = []
    file_path: Path | None = None
    digest: str | None = None
    actual_bounds: tuple[float, float, float, float] | None = None
    event_ids: set[str] = set()

    if not isinstance(descriptor, dict):
        return {
            "technical_status": "MISSING",
            "errors": [],
            "missing_fields": ["input descriptor"],
            "reviews": {axis: "MISSING" for axis in REVIEW_AXES},
            "_event_ids": set(),
        }

    required = (
        "path",
        "format",
        "sha256",
        "source_name",
        "source_id",
        "source_url",
        "retrieved_at_utc",
        "crs",
        "units",
    )
    for field in required:
        if _is_missing(descriptor.get(field)):
            missing.append(field)

    path_value = descriptor.get("path")
    if not _is_missing(path_value):
        try:
            candidate = (root / str(path_value)).resolve()
            candidate.relative_to(root)
            if not candidate.is_file():
                missing.append("file")
            else:
                file_path = candidate
        except (OSError, ValueError):
            errors.append("path must resolve to a file inside the project root.")

    format_value = str(descriptor.get("format", "")).strip().upper()
    crs_value = str(descriptor.get("crs", "")).strip().upper()
    if (
        not _is_missing(descriptor.get("crs"))
        and crs_value != "NOT_APPLICABLE"
        and not (
        _EPSG_PATTERN.fullmatch(crs_value) or crs_value == "OGC:CRS84"
        )
    ):
        errors.append("crs must use an EPSG code or OGC:CRS84.")
    if (
        name in {"terrain", "channel_geometry", "rainfall_forcing"}
        and not _is_missing(descriptor.get("crs"))
        and crs_value != "NOT_APPLICABLE"
        and model_horizontal_crs
        and crs_value != model_horizontal_crs.upper()
    ):
        errors.append(
            "crs does not match model.horizontal_crs; reproject and validate the model input first."
        )
    coordinate_columns = descriptor.get("coordinate_columns")
    if name == "gauge_metadata" and isinstance(coordinate_columns, dict):
        if (
            coordinate_columns.get("latitude") is not None
            and coordinate_columns.get("longitude") is not None
            and crs_value not in {"EPSG:4326", "OGC:CRS84"}
        ):
            errors.append(
                "gauge latitude/longitude columns must declare EPSG:4326 or OGC:CRS84."
            )
    if (
        format_value == "GEOJSON"
        and crs_value not in {"EPSG:4326", "OGC:CRS84"}
        and not _is_missing(descriptor.get("crs"))
    ):
        errors.append("GeoJSON coordinates must declare EPSG:4326 or OGC:CRS84.")
    source_url = descriptor.get("source_url")
    if not _is_missing(source_url):
        try:
            parsed_url = urlsplit(str(source_url))
        except ValueError:
            errors.append("source_url must be an HTTP(S) URL without embedded credentials.")
        else:
            if (
                parsed_url.scheme not in {"https", "http"}
                or not parsed_url.hostname
                or parsed_url.username is not None
                or parsed_url.password is not None
            ):
                errors.append(
                    "source_url must be an HTTP(S) URL without embedded credentials."
                )

    units = descriptor.get("units")
    if not _is_missing(units):
        if not isinstance(units, dict) or not units:
            errors.append("units must be a non-empty field-to-unit object.")
        else:
            for field, unit in units.items():
                if not isinstance(unit, str) or unit.strip().casefold() not in _ALLOWED_UNITS:
                    errors.append(f"units.{field} is missing or unsupported.")
                elif field == "rainfall" and model_rainfall_unit and (
                    _canonical_unit(unit) != _canonical_unit(model_rainfall_unit)
                ):
                    errors.append("units.rainfall does not match model.units.rainfall.")

    if name in VERTICAL_INPUTS:
        datum = descriptor.get("vertical_datum")
        if _is_missing(datum):
            missing.append("vertical_datum")
        elif model_vertical_datum and str(datum).strip() != model_vertical_datum:
            errors.append("vertical_datum does not match the declared model vertical datum.")
        vertical_unit = None
        if isinstance(units, dict):
            for field in _VERTICAL_UNIT_KEYS[name]:
                if units.get(field):
                    vertical_unit = str(units[field]).strip().casefold()
                    break
        if not vertical_unit:
            missing.append("vertical unit")
        elif model_vertical_unit and (
            _canonical_unit(vertical_unit) != _canonical_unit(model_vertical_unit)
        ):
            errors.append("vertical unit does not match the declared model vertical unit.")

    retrieved = descriptor.get("retrieved_at_utc")
    if not _is_missing(retrieved):
        try:
            _timestamp(retrieved, "retrieved_at_utc")
        except ValueError as error:
            errors.append(str(error))

    coverage = descriptor.get("coverage_bounds_wgs84")
    declared_coverage_bounds: tuple[float, float, float, float] | None = None
    if name in _GEOSPATIAL_INPUTS or name == "rainfall_forcing":
        if _is_missing(coverage):
            missing.append("coverage_bounds_wgs84")
        else:
            try:
                declared_coverage_bounds = _bounds(
                    coverage,
                    "coverage_bounds_wgs84",
                    allow_point_extent=True,
                )
                if study_bounds and not _intersects(
                    declared_coverage_bounds, study_bounds
                ):
                    errors.append("declared spatial coverage does not overlap the study area.")
            except ValueError as error:
                errors.append(str(error))

    if name in TIME_SERIES_INPUTS and _is_missing(descriptor.get("timestamp_column")):
        missing.append("timestamp_column")
    if name == "gauge_metadata" and _is_missing(descriptor.get("coordinate_columns")):
        missing.append("coordinate_columns")
    if name in {"calibration_observations", "validation_observations"} and _is_missing(
        descriptor.get("event_id_column")
    ):
        missing.append("event_id_column")

    if file_path:
        try:
            digest = _sha256_file(file_path)
        except OSError as error:
            errors.append(f"file could not be read: {error}")
        expected_digest = str(descriptor.get("sha256", "")).strip().lower()
        if not _is_missing(expected_digest):
            if not _SHA256_PATTERN.fullmatch(expected_digest):
                errors.append("sha256 must contain exactly 64 hexadecimal characters.")
            elif digest and digest != expected_digest:
                errors.append("sha256 does not match the current file.")

        try:
            if format_value in {"GEOJSON", "JSON"}:
                payload = json.loads(file_path.read_text(encoding="utf-8-sig"))
                if format_value == "GEOJSON" or name == "channel_geometry":
                    actual_bounds = _geojson_bounds(payload)
                    declared_file_crs = (
                        payload.get("crs", {}).get("properties", {}).get("name")
                        if isinstance(payload, dict)
                        and isinstance(payload.get("crs"), dict)
                        else None
                    )
                    if declared_file_crs:
                        normalized_file_crs = str(declared_file_crs).upper()
                        if normalized_file_crs not in {
                            crs_value,
                            "URN:OGC:DEF:CRS:OGC:1.3:CRS84",
                            "OGC:CRS84",
                            "EPSG:4326",
                        }:
                            errors.append(
                                "GeoJSON file CRS does not match its declared CRS metadata."
                            )
            elif format_value == "CSV":
                with file_path.open("r", encoding="utf-8-sig", newline="") as stream:
                    reader = csv.DictReader(stream)
                    if not reader.fieldnames:
                        raise ValueError("CSV has no header.")
                    required_columns = descriptor.get("required_columns", [])
                    if not isinstance(required_columns, list) or not required_columns:
                        missing.append("required_columns")
                    else:
                        absent = sorted(set(required_columns) - set(reader.fieldnames))
                        if absent:
                            errors.append(
                                f"CSV is missing required columns: {', '.join(absent)}."
                            )
                    timestamp_column = descriptor.get("timestamp_column")
                    interval_columns = descriptor.get("interval_columns")
                    coordinate_columns = descriptor.get("coordinate_columns")
                    event_id_column = descriptor.get("event_id_column")
                    series_key_columns = descriptor.get("series_key_columns", [])
                    if (
                        timestamp_column is not None
                        and timestamp_column not in reader.fieldnames
                    ):
                        errors.append("timestamp_column is absent from the CSV header.")
                    if interval_columns is not None and (
                        not isinstance(interval_columns, list)
                        or len(interval_columns) != 2
                        or any(column not in reader.fieldnames for column in interval_columns)
                    ):
                        errors.append("interval_columns must name two columns in the CSV.")
                    if coordinate_columns is not None and (
                        not isinstance(coordinate_columns, dict)
                        or coordinate_columns.get("latitude") not in reader.fieldnames
                        or coordinate_columns.get("longitude") not in reader.fieldnames
                    ):
                        errors.append(
                            "coordinate_columns must name latitude and longitude CSV columns."
                        )
                    if event_id_column is not None and event_id_column not in reader.fieldnames:
                        errors.append("event_id_column is absent from the CSV header.")
                    if not isinstance(series_key_columns, list) or any(
                        column not in reader.fieldnames for column in series_key_columns
                    ):
                        errors.append("series_key_columns must name CSV header columns.")
                        series_key_columns = []
                    previous_timestamps: dict[tuple[str, ...], datetime] = {}
                    row_count = 0
                    for row_number, row in enumerate(reader, start=2):
                        row_count += 1
                        if (
                            name in TIME_SERIES_INPUTS
                            and timestamp_column in reader.fieldnames
                        ):
                            try:
                                current = _timestamp(
                                    row.get(timestamp_column),
                                    f"CSV row {row_number} {timestamp_column}",
                                )
                            except ValueError as error:
                                errors.append(str(error))
                            else:
                                series_key = tuple(
                                    str(row.get(column, "")).strip()
                                    for column in series_key_columns
                                )
                                previous = previous_timestamps.get(series_key)
                                if previous is not None and current <= previous:
                                    errors.append(
                                        "time-series timestamps must be strictly increasing and unique per series."
                                    )
                                previous_timestamps[series_key] = current
                        if isinstance(interval_columns, list) and len(interval_columns) == 2:
                            start_column, end_column = interval_columns
                            try:
                                start = _timestamp(
                                    row.get(start_column),
                                    f"CSV row {row_number} {start_column}",
                                )
                                end = _timestamp(
                                    row.get(end_column),
                                    f"CSV row {row_number} {end_column}",
                                )
                            except ValueError as error:
                                errors.append(str(error))
                            else:
                                if start >= end:
                                    errors.append(
                                        f"CSV row {row_number} interval start must be before interval end."
                                    )
                        if isinstance(coordinate_columns, dict):
                            lat_column = coordinate_columns.get("latitude")
                            lon_column = coordinate_columns.get("longitude")
                            if lat_column not in reader.fieldnames or lon_column not in reader.fieldnames:
                                errors.append("coordinate_columns are absent from the CSV header.")
                            else:
                                try:
                                    latitude = float(row[lat_column])
                                    longitude = float(row[lon_column])
                                    if (
                                        not math.isfinite(latitude)
                                        or not math.isfinite(longitude)
                                        or not -90 <= latitude <= 90
                                        or not -180 <= longitude <= 180
                                    ):
                                        raise ValueError
                                except (TypeError, ValueError):
                                    errors.append(
                                        f"CSV row {row_number} has invalid latitude/longitude coordinates."
                                    )
                                else:
                                    if declared_coverage_bounds is None:
                                        errors.append(
                                            "coordinate validation requires coverage_bounds_wgs84."
                                        )
                                    else:
                                        if not (
                                            declared_coverage_bounds[0] <= longitude <= declared_coverage_bounds[2]
                                            and declared_coverage_bounds[1] <= latitude <= declared_coverage_bounds[3]
                                        ):
                                            errors.append(
                                                f"CSV row {row_number} coordinates fall outside declared coverage."
                                            )
                        if isinstance(event_id_column, str):
                            event_id = str(row.get(event_id_column, "")).strip()
                            if not event_id:
                                errors.append(
                                    f"CSV row {row_number} event identifier is missing."
                                )
                            else:
                                event_ids.add(event_id)
                    if row_count == 0:
                        errors.append("CSV contains no records.")
            elif format_value in {"GEOTIFF", "TIFF"}:
                _validate_tiff(file_path, format_value == "GEOTIFF")
                resolution = descriptor.get("resolution")
                if not isinstance(resolution, (list, tuple)) or len(resolution) != 2:
                    missing.append("resolution")
                else:
                    try:
                        values = [float(item) for item in resolution]
                    except (TypeError, ValueError):
                        values = []
                    if len(values) != 2 or not all(
                        math.isfinite(item) and item > 0 for item in values
                    ):
                        errors.append("resolution must contain two positive finite values.")
            else:
                errors.append("format must be CSV, JSON, GeoJSON, TIFF, or GeoTIFF.")
        except (OSError, UnicodeError, csv.Error, json.JSONDecodeError, ValueError) as error:
            errors.append(f"file format validation failed: {error}")

        if actual_bounds and study_bounds and not _intersects(actual_bounds, study_bounds):
            errors.append("file coordinates do not overlap the study area.")

    review_references = descriptor.get("review_evidence", {})
    if not isinstance(review_references, dict):
        review_references = {}
    reviews = {
        axis: "UNVERIFIED" if not _is_missing(review_references.get(axis)) else "MISSING"
        for axis in REVIEW_AXES
    }

    status = "INVALID" if errors else "MISSING" if missing else "READY"
    return {
        "technical_status": status,
        "errors": sorted(set(errors)),
        "missing_fields": sorted(set(missing)),
        "reviews": reviews,
        "sha256": digest,
        "_event_ids": event_ids,
    }


def validate_model_configuration(
    configuration: Any,
    project_root: str | Path,
) -> dict[str, Any]:
    """Validate technical declarations only; never authorizes or executes a model."""
    root = Path(project_root).resolve()
    errors: list[str] = []
    missing: list[str] = []
    if not isinstance(configuration, dict):
        return {
            "technical_status": "INVALID",
            "execution_status": "NOT_READY",
            "execution_permitted": False,
            "errors": ["configuration must be a JSON object."],
            "missing_fields": [],
            "inputs": {},
        }

    if configuration.get("configuration_version") != "1.0":
        errors.append("configuration_version must be '1.0'.")
    if configuration.get("execution_enabled") is not False:
        errors.append("execution_enabled must remain false in this preparation scaffold.")

    model = configuration.get("model")
    if not isinstance(model, dict):
        missing.append("model")
        model = {}
    for field in ("name", "version", "horizontal_crs", "vertical_datum"):
        if _is_missing(model.get(field)):
            missing.append(f"model.{field}")
    if _is_missing(model.get("solver_family")) or str(
        model.get("solver_family", "")
    ).strip().upper() == "UNSELECTED":
        missing.append("model.solver_family")
    horizontal_crs = str(model.get("horizontal_crs", "")).strip().upper()
    if not _is_missing(model.get("horizontal_crs")) and (
        not _EPSG_PATTERN.fullmatch(horizontal_crs)
        or horizontal_crs in {"EPSG:4326", "EPSG:4269", "EPSG:4258"}
    ):
        errors.append("model.horizontal_crs must be a projected EPSG CRS, not a geographic CRS.")
    units = model.get("units")
    vertical_unit: str | None = None
    rainfall_unit: str | None = None
    if not isinstance(units, dict):
        missing.append("model.units")
    else:
        for field in ("horizontal", "vertical", "flow", "rainfall"):
            if _is_missing(units.get(field)):
                missing.append(f"model.units.{field}")
            elif (
                not isinstance(units[field], str)
                or units[field].strip().casefold() not in _ALLOWED_UNITS
            ):
                errors.append(f"model.units.{field} is unsupported.")
        if isinstance(units.get("vertical"), str):
            vertical_unit = units["vertical"].strip()
        if isinstance(units.get("rainfall"), str):
            rainfall_unit = units["rainfall"].strip()
        if units.get("horizontal") and str(units["horizontal"]).strip().casefold() not in {
            "m", "meter", "meters", "metre", "metres", "ft", "foot", "feet",
        }:
            errors.append("model.units.horizontal must be a projected length unit (m or ft).")

    study_area = configuration.get("study_area")
    study_bounds: tuple[float, float, float, float] | None = None
    if not isinstance(study_area, dict):
        missing.append("study_area")
        study_area = {}
    if _is_missing(study_area.get("name")):
        missing.append("study_area.name")
    if str(study_area.get("crs", "")).strip().upper() not in {
        "EPSG:4326", "OGC:CRS84",
    }:
        errors.append("study_area.crs must be EPSG:4326 or OGC:CRS84 for WGS 84 bounds.")
    try:
        study_bounds = _bounds(study_area.get("bounds_wgs84"), "study_area.bounds_wgs84")
    except ValueError as error:
        if _is_missing(study_area.get("bounds_wgs84")):
            missing.append("study_area.bounds_wgs84")
        else:
            errors.append(str(error))

    time_window = configuration.get("time_window")
    if not isinstance(time_window, dict):
        missing.append("time_window")
        time_window = {}
    parsed_times: dict[str, datetime] = {}
    for field in ("start_utc", "end_utc"):
        if _is_missing(time_window.get(field)):
            missing.append(f"time_window.{field}")
        else:
            try:
                parsed_times[field] = _timestamp(
                    time_window[field], f"time_window.{field}"
                )
            except ValueError as error:
                errors.append(str(error))
    if (
        "start_utc" in parsed_times
        and "end_utc" in parsed_times
        and parsed_times["start_utc"] >= parsed_times["end_utc"]
    ):
        errors.append("time_window.start_utc must be before end_utc.")
    step = time_window.get("time_step_seconds")
    if _is_missing(step):
        missing.append("time_window.time_step_seconds")
    else:
        try:
            step_value = float(step)
            if not math.isfinite(step_value) or step_value <= 0:
                raise ValueError
        except (TypeError, ValueError):
            errors.append("time_window.time_step_seconds must be positive and finite.")

    if _is_missing(configuration.get("output_directory")):
        missing.append("output_directory")

    input_config = configuration.get("inputs")
    if not isinstance(input_config, dict):
        missing.append("inputs")
        input_config = {}
    input_results: dict[str, dict[str, Any]] = {}
    model_datum = (
        str(model.get("vertical_datum")).strip()
        if not _is_missing(model.get("vertical_datum"))
        else None
    )
    for name in REQUIRED_INPUTS:
        result = _file_status(
            name,
            input_config.get(name),
            root,
            study_bounds,
            horizontal_crs if not _is_missing(model.get("horizontal_crs")) else None,
            model_datum,
            vertical_unit,
            rainfall_unit,
        )
        input_results[name] = result
        errors.extend(f"inputs.{name}: {error}" for error in result["errors"])
        missing.extend(
            f"inputs.{name}.{field}" for field in result["missing_fields"]
        )

    event_ids = {
        name: result.pop("_event_ids", set())
        for name, result in input_results.items()
    }
    calibration_ids = event_ids["calibration_observations"]
    validation_ids = event_ids["validation_observations"]
    if calibration_ids & validation_ids:
        overlap = sorted(calibration_ids & validation_ids)
        message = (
            "calibration and validation event IDs overlap; keep validation events independent."
        )
        errors.append(message)
        for name in ("calibration_observations", "validation_observations"):
            input_results[name]["errors"].append(message)
            input_results[name]["errors"].sort()
            input_results[name]["technical_status"] = "INVALID"

    if errors:
        technical_status = "INVALID"
    elif missing:
        technical_status = "MISSING"
    else:
        technical_status = "READY"

    return {
        "technical_status": technical_status,
        "execution_status": "NOT_READY",
        "execution_permitted": False,
        "errors": sorted(set(errors)),
        "missing_fields": sorted(set(missing)),
        "review_statuses": {axis: "UNVERIFIED" for axis in REVIEW_AXES},
        "inputs": input_results,
        "limitations": [
            "File structure and declared metadata do not authenticate a source or verify licensing.",
            "Domain approval and scientific suitability require independent review.",
            "The preflight does not run a solver or establish calibration, validation, or forecast accuracy.",
            "Existing gauge-package and flood-target readiness checks remain authoritative for those separate workflows.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run non-operational hydraulic model input/configuration checks."
    )
    parser.add_argument("--config", required=True, help="Path to a JSON configuration.")
    parser.add_argument(
        "--project-root",
        default=".",
        help="Project root used to resolve input paths (default: current directory).",
    )
    args = parser.parse_args()
    try:
        config_path = Path(args.config).resolve()
        configuration = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        print(json.dumps({"technical_status": "INVALID", "error": str(error)}, indent=2))
        raise SystemExit(2) from error
    result = validate_model_configuration(configuration, args.project_root)
    print(json.dumps(result, indent=2, sort_keys=True))
    if result["technical_status"] != "READY":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
