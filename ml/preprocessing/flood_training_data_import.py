from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ml.preprocessing.file_integrity import sha256_file
from ml.preprocessing.flood_environmental_dataset import FEATURE_COLUMNS, TARGET_ID

UTC = timezone.utc
OBSERVATION_COLUMNS = (
    "gauge_id",
    "source_record_id",
    "observed_at",
    "water_level_m",
    "vertical_datum",
    "quality_flag",
)
DANGER_LEVEL_COLUMNS = (
    "gauge_id",
    "threshold_record_id",
    "effective_from",
    "effective_to",
    "danger_level_m",
    "vertical_datum",
    "unit",
)
CROSSWALK_COLUMNS = (
    "gauge_id",
    "grid_location_id",
    "gauge_latitude",
    "gauge_longitude",
    "grid_latitude",
    "grid_longitude",
    "approved_max_distance_km",
    "review_status",
    "reviewer",
    "reviewed_at_utc",
    "reference",
    "matching_method",
)
COVERAGE_COLUMNS = (
    "gauge_id",
    "window_start_utc",
    "window_end_utc",
    "expected_interval_minutes",
    "complete_status",
    "evidence_reference",
    "source_record_id",
)
PREDICTOR_COLUMNS = (
    "location_id",
    "grid_latitude",
    "grid_longitude",
    "prediction_issue_time_utc",
    "candidate_target_window_start_utc",
    "candidate_target_window_end_utc",
    *FEATURE_COLUMNS,
)
METADATA_SOURCES = (
    "observations",
    "danger_levels",
    "crosswalk",
    "coverage",
    "predictors",
)
SOURCE_METADATA_FIELDS = (
    "source_name",
    "source_url",
    "access_status",
    "license_status",
    "license_reference",
    "license_evidence_reference",
    "retrieved_at_utc",
    "source_timezone",
    "raw_source_file",
    "raw_source_sha256",
    "field_mapping_reference",
)
VALID_QUALITY_FLAGS = {"VALID", "GOOD", "APPROVED"}
TARGET_HOURS = 24


def _read_csv(path: str | Path, required: tuple[str, ...], dataset: str) -> list[dict[str, str]]:
    source = Path(path)
    with source.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None:
            raise ValueError(f"{dataset} CSV has no header.")
        missing = set(required) - set(reader.fieldnames)
        if missing:
            raise ValueError(f"{dataset} CSV is missing columns: {', '.join(sorted(missing))}.")
        rows = list(reader)
    if not rows:
        raise ValueError(f"{dataset} CSV contains no records.")
    return rows


def _text(row: dict[str, Any], field: str, dataset: str) -> str:
    value = str(row.get(field, "")).strip()
    if not value:
        raise ValueError(f"{dataset} field {field!r} must not be empty.")
    return value


def _parse_timestamp(value: Any, field: str, source_timezone: str | None = None) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} timestamp is missing.")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.strptime(text, "%d-%m-%Y %H:%M")
        except ValueError as error:
            raise ValueError(
                f"{field} must be ISO-8601 or DD-MM-YYYY HH:MM and have an explicit timezone "
                "or declared source timezone."
            ) from error
    if parsed.tzinfo is None:
        if not source_timezone:
            raise ValueError(
                f"{field} is timezone-naive; provide the documented source_timezone explicitly."
            )
        try:
            zone = ZoneInfo(source_timezone)
        except ZoneInfoNotFoundError as error:
            raise ValueError(f"Unknown IANA source timezone {source_timezone!r}.") from error
        earlier = parsed.replace(tzinfo=zone, fold=0)
        later = parsed.replace(tzinfo=zone, fold=1)
        if earlier.utcoffset() != later.utcoffset():
            raise ValueError(f"{field} is ambiguous in source timezone {source_timezone!r}.")
        if earlier.astimezone(UTC).astimezone(zone).replace(tzinfo=None) != parsed:
            raise ValueError(f"{field} does not exist in source timezone {source_timezone!r}.")
        parsed = earlier
    return parsed.astimezone(UTC)


def _number(value: Any, field: str, *, minimum: float | None = None) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must be numeric.") from error
    if not math.isfinite(result) or (minimum is not None and result < minimum):
        raise ValueError(f"{field} must be finite and at least {minimum}.")
    return result


def _check_coordinates(row: dict[str, Any], lat_field: str, lon_field: str, dataset: str) -> tuple[float, float]:
    latitude = _number(row.get(lat_field), f"{dataset}.{lat_field}")
    longitude = _number(row.get(lon_field), f"{dataset}.{lon_field}")
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError(f"{dataset} coordinates are outside WGS 84 bounds.")
    return latitude, longitude


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0088
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    value = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * radius_km * math.asin(math.sqrt(min(1.0, value)))


def _load_metadata(path: str | Path) -> dict[str, dict[str, str]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    sources = payload.get("sources")
    if not isinstance(sources, dict):
        raise ValueError("Source metadata JSON must contain a 'sources' object.")
    missing_sources = set(METADATA_SOURCES) - set(sources)
    if missing_sources:
        raise ValueError(
            "Source metadata is missing entries: " + ", ".join(sorted(missing_sources)) + "."
        )
    result: dict[str, dict[str, str]] = {}
    metadata_directory = Path(path).resolve().parent
    for name in METADATA_SOURCES:
        metadata = sources[name]
        if not isinstance(metadata, dict):
            raise ValueError(f"Source metadata for {name!r} must be an object.")
        result[name] = {
            field: _text(metadata, field, f"source metadata {name}")
            for field in SOURCE_METADATA_FIELDS
        }
        _parse_timestamp(result[name]["retrieved_at_utc"], f"{name}.retrieved_at_utc")
        if len(result[name]["raw_source_sha256"]) != 64 or any(
            character not in "0123456789abcdefABCDEF"
            for character in result[name]["raw_source_sha256"]
        ):
            raise ValueError(f"{name}.raw_source_sha256 must be a 64-character hexadecimal SHA-256.")
        raw_source_path = Path(result[name]["raw_source_file"])
        if not raw_source_path.is_absolute():
            raw_source_path = metadata_directory / raw_source_path
        if not raw_source_path.is_file():
            raise ValueError(
                f"Original raw source file for {name!r} is missing: {raw_source_path}."
            )
        actual_hash = sha256_file(raw_source_path)
        if actual_hash.lower() != result[name]["raw_source_sha256"].lower():
            raise ValueError(f"Original raw source SHA-256 does not match for {name!r}.")
        result[name]["raw_source_file"] = str(raw_source_path.resolve())
        result[name]["raw_source_sha256"] = actual_hash
    return result


def _validate_observations(
    rows: list[dict[str, str]],
    source_timezone: str | None,
) -> tuple[dict[str, list[dict[str, Any]]], int]:
    by_gauge: dict[str, list[dict[str, Any]]] = {}
    seen: set[tuple[str, datetime]] = set()
    invalid_quality_count = 0
    for row in rows:
        gauge_id = _text(row, "gauge_id", "observations")
        record_id = _text(row, "source_record_id", "observations")
        timestamp = _parse_timestamp(row["observed_at"], "observed_at", source_timezone)
        key = (gauge_id, timestamp)
        if key in seen:
            raise ValueError(
                f"Duplicate observation for gauge {gauge_id!r} at {timestamp.isoformat()}."
            )
        seen.add(key)
        quality = _text(row, "quality_flag", "observations").upper()
        vertical_datum = _text(row, "vertical_datum", "observations")
        if vertical_datum.upper() in {"UNKNOWN", "UNVERIFIED", "NA", "N/A"}:
            raise ValueError(f"Observation vertical datum is not established for gauge {gauge_id!r}.")
        water_level: float | None = None
        raw_level = str(row.get("water_level_m", "")).strip()
        if raw_level:
            water_level = _number(raw_level, "water_level_m")
        valid = quality in VALID_QUALITY_FLAGS and water_level is not None
        if not valid:
            invalid_quality_count += 1
        by_gauge.setdefault(gauge_id, []).append(
            {
                "source_record_id": record_id,
                "observed_at": timestamp,
                "water_level_m": water_level,
                "vertical_datum": vertical_datum,
                "quality_flag": quality,
                "valid": valid,
            }
        )
    for items in by_gauge.values():
        items.sort(key=lambda item: item["observed_at"])
    return by_gauge, invalid_quality_count


def _validate_thresholds(rows: list[dict[str, str]]) -> dict[str, list[dict[str, Any]]]:
    by_gauge: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        gauge_id = _text(row, "gauge_id", "danger levels")
        unit = _text(row, "unit", "danger levels")
        if unit != "m":
            raise ValueError(f"Danger-level unit must be 'm'; got {unit!r}.")
        start = _parse_timestamp(row["effective_from"], "effective_from")
        end = _parse_timestamp(row["effective_to"], "effective_to")
        if end <= start:
            raise ValueError(f"Danger-level interval for gauge {gauge_id!r} must have positive duration.")
        value = _number(row["danger_level_m"], "danger_level_m")
        vertical_datum = _text(row, "vertical_datum", "danger levels")
        if vertical_datum.upper() in {"UNKNOWN", "UNVERIFIED", "NA", "N/A"}:
            raise ValueError(f"Danger-level vertical datum is not established for gauge {gauge_id!r}.")
        by_gauge.setdefault(gauge_id, []).append(
            {
                "threshold_record_id": _text(row, "threshold_record_id", "danger levels"),
                "effective_from": start,
                "effective_to": end,
                "danger_level_m": value,
                "vertical_datum": vertical_datum,
            }
        )
    for gauge_id, intervals in by_gauge.items():
        intervals.sort(key=lambda item: item["effective_from"])
        for previous, current in zip(intervals, intervals[1:]):
            if current["effective_from"] < previous["effective_to"]:
                raise ValueError(f"Danger-level effective intervals overlap for gauge {gauge_id!r}.")
    return by_gauge


def _validate_crosswalk(rows: list[dict[str, str]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        gauge_id = _text(row, "gauge_id", "crosswalk")
        if gauge_id in result:
            raise ValueError(f"Crosswalk contains duplicate gauge mapping for {gauge_id!r}.")
        grid_id = _text(row, "grid_location_id", "crosswalk")
        gauge_lat, gauge_lon = _check_coordinates(
            row, "gauge_latitude", "gauge_longitude", "crosswalk"
        )
        grid_lat, grid_lon = _check_coordinates(
            row, "grid_latitude", "grid_longitude", "crosswalk"
        )
        max_distance = _number(
            row.get("approved_max_distance_km"),
            "approved_max_distance_km",
            minimum=0,
        )
        if _text(row, "review_status", "crosswalk").upper() != "APPROVED":
            raise ValueError(f"Gauge mapping for {gauge_id!r} is not explicitly approved.")
        reviewer = _text(row, "reviewer", "crosswalk")
        reference = _text(row, "reference", "crosswalk")
        method = _text(row, "matching_method", "crosswalk")
        reviewed_at = _parse_timestamp(row["reviewed_at_utc"], "reviewed_at_utc")
        distance = _haversine_km(gauge_lat, gauge_lon, grid_lat, grid_lon)
        if distance > max_distance:
            raise ValueError(
                f"Gauge/grid distance for {gauge_id!r} is {distance:.3f} km, exceeding the "
                f"reviewed limit of {max_distance:.3f} km."
            )
        result[gauge_id] = {
            "grid_location_id": grid_id,
            "distance_km": distance,
            "grid_latitude": grid_lat,
            "grid_longitude": grid_lon,
            "approved_max_distance_km": max_distance,
            "reviewer": reviewer,
            "reference": reference,
            "matching_method": method,
            "reviewed_at_utc": reviewed_at,
        }
    return result


def _validate_coverage(rows: list[dict[str, str]]) -> dict[str, list[dict[str, Any]]]:
    by_gauge: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        gauge_id = _text(row, "gauge_id", "coverage")
        start = _parse_timestamp(row["window_start_utc"], "window_start_utc")
        end = _parse_timestamp(row["window_end_utc"], "window_end_utc")
        if end <= start:
            raise ValueError(f"Coverage interval for gauge {gauge_id!r} must have positive duration.")
        interval = int(_number(row["expected_interval_minutes"], "expected_interval_minutes", minimum=1))
        if float(interval) != _number(row["expected_interval_minutes"], "expected_interval_minutes", minimum=1):
            raise ValueError("expected_interval_minutes must be a positive whole number.")
        by_gauge.setdefault(gauge_id, []).append(
            {
                "start": start,
                "end": end,
                "interval_minutes": interval,
                "status": _text(row, "complete_status", "coverage").upper(),
                "evidence_reference": _text(row, "evidence_reference", "coverage"),
                "source_record_id": _text(row, "source_record_id", "coverage"),
            }
        )
    return by_gauge


def _interval_for_window(
    intervals: list[dict[str, Any]] | None,
    start: datetime,
    end: datetime,
) -> dict[str, Any] | None:
    matches = [
        item
        for item in (intervals or [])
        if item["start"] <= start and item["end"] >= end
    ]
    return matches[0] if len(matches) == 1 else None


def _window_times(start: datetime, end: datetime, interval_minutes: int) -> set[datetime]:
    step = timedelta(minutes=interval_minutes)
    duration_seconds = (end - start).total_seconds()
    if duration_seconds % step.total_seconds():
        return set()
    return {start + offset * step for offset in range(int(duration_seconds // step.total_seconds()))}


def _assess_window(
    *,
    gauge_id: str,
    grid_location_id: str,
    issue_time: datetime,
    observations: dict[str, list[dict[str, Any]]],
    thresholds: dict[str, list[dict[str, Any]]],
    coverage: dict[str, list[dict[str, Any]]],
    crosswalk: dict[str, Any],
    predictor_grid_latitude: float,
    predictor_grid_longitude: float,
) -> dict[str, Any]:
    window_end = issue_time + timedelta(hours=TARGET_HOURS)
    effective = [
        row
        for row in thresholds.get(gauge_id, [])
        if row["effective_from"] <= issue_time and row["effective_to"] >= window_end
    ]
    if len(effective) != 1:
        status = "INDETERMINATE_DANGER_LEVEL"
        threshold = None
    else:
        status = "INDETERMINATE"
        threshold = effective[0]
    samples = [
        row for row in observations.get(gauge_id, [])
        if issue_time <= row["observed_at"] < window_end
    ]
    valid_samples = [row for row in samples if row["valid"]]
    if threshold is not None and any(
        row["vertical_datum"] != threshold["vertical_datum"] for row in valid_samples
    ):
        threshold = None
        status = "INDETERMINATE_VERTICAL_DATUM"
    exceedances = [
        row for row in valid_samples
        if threshold is not None and row["water_level_m"] >= threshold["danger_level_m"]
    ]
    coverage_record = _interval_for_window(coverage.get(gauge_id), issue_time, window_end)
    if threshold is not None and exceedances:
        status = "POSITIVE_EVIDENCE_CHECKS_PASSED"
    elif threshold is not None and coverage_record is not None:
        expected = _window_times(issue_time, window_end, coverage_record["interval_minutes"])
        observed_valid = {row["observed_at"] for row in valid_samples}
        has_invalid_in_window = len(valid_samples) != len(samples)
        complete = (
            coverage_record["status"] == "CONFIRMED_COMPLETE"
            and bool(expected)
            and observed_valid == expected
            and not has_invalid_in_window
        )
        if complete and all(
            row["water_level_m"] < threshold["danger_level_m"] for row in valid_samples
        ):
            status = "NEGATIVE_EVIDENCE_CHECKS_PASSED"
        else:
            status = "INDETERMINATE_INCOMPLETE_COVERAGE"
    elif threshold is not None and not exceedances:
        status = "INDETERMINATE_NO_COVERAGE_EVIDENCE"
    if (
        crosswalk["grid_location_id"] != grid_location_id
        or abs(crosswalk["grid_latitude"] - predictor_grid_latitude) > 1e-4
        or abs(crosswalk["grid_longitude"] - predictor_grid_longitude) > 1e-4
    ):
        status = "INDETERMINATE_GAUGE_GRID_MISMATCH"
    return {
        "target_id": TARGET_ID,
        "gauge_id": gauge_id,
        "grid_location_id": grid_location_id,
        "location_crosswalk_reference": crosswalk["reference"],
        "prediction_issue_time_utc": issue_time.isoformat().replace("+00:00", "Z"),
        "target_window_start_utc": issue_time.isoformat().replace("+00:00", "Z"),
        "target_window_end_utc": window_end.isoformat().replace("+00:00", "Z"),
        "assessment": status,
        "danger_level_m": threshold["danger_level_m"] if threshold else None,
        "danger_level_source_record_id": threshold["threshold_record_id"] if threshold else None,
        "maximum_observed_stage_m": (
            max((row["water_level_m"] for row in valid_samples), default=None)
        ),
        "valid_observation_count": len(valid_samples),
        "expected_observation_count": (
            len(_window_times(issue_time, window_end, coverage_record["interval_minutes"]))
            if coverage_record else None
        ),
        "observation_source_record_ids": ";".join(
            row["source_record_id"] for row in valid_samples
        ),
        "coverage_evidence_reference": (
            coverage_record["evidence_reference"] if coverage_record else ""
        ),
        "coverage_source_record_id": (
            coverage_record["source_record_id"] if coverage_record else ""
        ),
        "crosswalk_distance_km": crosswalk["distance_km"],
        "crosswalk_matching_method": crosswalk["matching_method"],
    }


def assess_training_data_bundle(
    *,
    observations_path: str | Path,
    danger_levels_path: str | Path,
    crosswalk_path: str | Path,
    coverage_path: str | Path,
    predictors_path: str | Path,
    source_metadata_path: str | Path,
    output_path: str | Path,
    observation_timezone: str | None = None,
) -> dict[str, Any]:
    source_paths = {
        "observations": Path(observations_path),
        "danger_levels": Path(danger_levels_path),
        "crosswalk": Path(crosswalk_path),
        "coverage": Path(coverage_path),
        "predictors": Path(predictors_path),
    }
    if observation_timezone:
        try:
            ZoneInfo(observation_timezone)
        except ZoneInfoNotFoundError as error:
            raise ValueError(f"Unknown IANA observation timezone {observation_timezone!r}.") from error
    metadata = _load_metadata(source_metadata_path)
    declared_observation_timezone = metadata["observations"]["source_timezone"]
    try:
        ZoneInfo(declared_observation_timezone)
    except ZoneInfoNotFoundError as error:
        raise ValueError(
            "Source metadata observations.source_timezone must be a valid IANA timezone."
        ) from error
    if observation_timezone and observation_timezone != declared_observation_timezone:
        raise ValueError(
            "--observation-timezone must match the observation source metadata declaration."
        )
    effective_observation_timezone = observation_timezone or declared_observation_timezone
    observation_rows = _read_csv(source_paths["observations"], OBSERVATION_COLUMNS, "observations")
    danger_rows = _read_csv(source_paths["danger_levels"], DANGER_LEVEL_COLUMNS, "danger levels")
    crosswalk_rows = _read_csv(source_paths["crosswalk"], CROSSWALK_COLUMNS, "crosswalk")
    coverage_rows = _read_csv(source_paths["coverage"], COVERAGE_COLUMNS, "coverage")
    predictor_rows = _read_csv(source_paths["predictors"], PREDICTOR_COLUMNS, "predictors")

    observations, invalid_quality_count = _validate_observations(
        observation_rows, effective_observation_timezone
    )
    thresholds = _validate_thresholds(danger_rows)
    crosswalk = _validate_crosswalk(crosswalk_rows)
    coverage = _validate_coverage(coverage_rows)
    assessments = []
    seen_predictor_windows: set[tuple[str, datetime]] = set()
    for predictor in predictor_rows:
        grid_id = _text(predictor, "location_id", "predictors")
        issue_time = _parse_timestamp(
            predictor["prediction_issue_time_utc"], "prediction_issue_time_utc"
        )
        declared_start = _parse_timestamp(
            predictor["candidate_target_window_start_utc"],
            "candidate_target_window_start_utc",
        )
        declared_end = _parse_timestamp(
            predictor["candidate_target_window_end_utc"],
            "candidate_target_window_end_utc",
        )
        if declared_start != issue_time or declared_end != issue_time + timedelta(hours=TARGET_HOURS):
            raise ValueError(
                "Predictor target window must equal the half-open 24-hour UTC window beginning at issue time."
            )
        predictor_grid_latitude, predictor_grid_longitude = _check_coordinates(
            predictor, "grid_latitude", "grid_longitude", "predictors"
        )
        predictor_key = (grid_id, issue_time)
        if predictor_key in seen_predictor_windows:
            raise ValueError(f"Duplicate predictor issue window for grid {grid_id!r}.")
        seen_predictor_windows.add(predictor_key)
        for feature in FEATURE_COLUMNS:
            _number(predictor.get(feature), f"predictors.{feature}")
        mapped_gauges = [
            gauge_id for gauge_id, item in crosswalk.items()
            if item["grid_location_id"] == grid_id
        ]
        if not mapped_gauges:
            assessments.append(
                {
                    "target_id": TARGET_ID,
                    "grid_location_id": grid_id,
                    "prediction_issue_time_utc": issue_time.isoformat().replace("+00:00", "Z"),
                    "target_window_start_utc": issue_time.isoformat().replace("+00:00", "Z"),
                    "target_window_end_utc": (
                        issue_time + timedelta(hours=TARGET_HOURS)
                    ).isoformat().replace("+00:00", "Z"),
                    "assessment": "INDETERMINATE_NO_REVIEWED_CROSSWALK",
                }
            )
            continue
        for gauge_id in mapped_gauges:
            assessments.append(
                _assess_window(
                    gauge_id=gauge_id,
                    grid_location_id=grid_id,
                    issue_time=issue_time,
                    observations=observations,
                    thresholds=thresholds,
                    coverage=coverage,
                    crosswalk=crosswalk[gauge_id],
                    predictor_grid_latitude=predictor_grid_latitude,
                    predictor_grid_longitude=predictor_grid_longitude,
                )
            )

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in assessments for key in row})
    with destination.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(assessments)

    counts: dict[str, int] = {}
    for item in assessments:
        status = str(item["assessment"])
        counts[status] = counts.get(status, 0) + 1
    manifest = {
        "manifest_version": "1.0",
        "target_id": TARGET_ID,
        "prediction_horizon_hours": TARGET_HOURS,
        "status": "NOT_READY",
        "status_reason": (
            "This assessment does not approve the target, authenticate source quality or licensing, "
            "establish representative multi-site samples, train/evaluate a model, or enable inference."
        ),
        "input_files": {
            name: {
                "path": str(path),
                "sha256": sha256_file(path),
                "raw_source_file": metadata[name]["raw_source_file"],
                "raw_source_sha256": metadata[name]["raw_source_sha256"],
                "source_metadata": metadata[name],
            }
            for name, path in source_paths.items()
        },
        "source_metadata_file": {
            "path": str(Path(source_metadata_path)),
            "sha256": sha256_file(source_metadata_path),
            "interpretation": "User-supplied provenance assertions; not independently authenticated.",
        },
        "observation_timezone_for_naive_values": effective_observation_timezone,
        "invalid_or_unusable_observations": invalid_quality_count,
        "assessment_counts": counts,
        "assessment_rows": len(assessments),
        "output_file": destination.name,
        "output_sha256": sha256_file(destination),
        "crosswalk_uncertainty": (
            "Coordinate distance is an audit metric only. A reviewed coordinate proximity does not "
            "establish catchment membership, hydraulic connectivity, upstream position, or forecast "
            "lead-time relevance."
        ),
    }
    manifest_path = destination.with_suffix(".manifest.json")
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Validate authorized flood-training source files and assess exact 24-hour windows. "
            "This does not train a model or promote readiness."
        )
    )
    for argument in (
        "observations",
        "danger-levels",
        "crosswalk",
        "coverage",
        "predictors",
        "source-metadata",
        "output",
    ):
        parser.add_argument(f"--{argument}", type=Path, required=True)
    parser.add_argument(
        "--observation-timezone",
        help="Required only when source observation timestamps lack timezone information.",
    )
    args = parser.parse_args()
    try:
        manifest = assess_training_data_bundle(
            observations_path=args.observations,
            danger_levels_path=args.danger_levels,
            crosswalk_path=args.crosswalk,
            coverage_path=args.coverage,
            predictors_path=args.predictors,
            source_metadata_path=args.source_metadata,
            output_path=args.output,
            observation_timezone=args.observation_timezone,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
