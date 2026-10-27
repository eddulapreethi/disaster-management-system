from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ml.preprocessing.file_integrity import sha256_file
from ml.preprocessing.flood_environmental_dataset import build_predictor_frame
from ml.preprocessing.flood_training_data_import import (
    CROSSWALK_COLUMNS,
    COVERAGE_COLUMNS,
    DANGER_LEVEL_COLUMNS,
    METADATA_SOURCES,
    OBSERVATION_COLUMNS,
    SOURCE_METADATA_FIELDS,
    _check_coordinates,
    _load_metadata,
    _parse_timestamp,
    _read_csv,
    _validate_coverage,
    _validate_crosswalk,
    _validate_observations,
    _validate_thresholds,
)
from ml.preprocessing.normalize_nwdp_observations import MAPPING_COLUMNS

TEST_SENTINELS = {"ILLUSTRATIVE_ONLY", "TEST_ONLY", "SYNTHETIC", "EXAMPLE_ONLY"}
UNVERIFIED_SENTINELS = {"", "UNVERIFIED", "UNKNOWN", "NA", "N/A", "NONE", "NULL"}


def _contains_sentinel(value: Any, sentinels: set[str]) -> bool:
    if isinstance(value, dict):
        return any(_contains_sentinel(item, sentinels) for item in value.values())
    if isinstance(value, list):
        return any(_contains_sentinel(item, sentinels) for item in value)
    if isinstance(value, str):
        normalized = value.strip().upper()
        return normalized in sentinels or any(
            sentinel in normalized for sentinel in TEST_SENTINELS
        )
    return False


def _requirement(
    status: str,
    *,
    path: str | None,
    details: str,
    missing_files: list[str] | None = None,
    invalid_fields: list[str] | None = None,
    evidence_needed: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "path": path,
        "details": details,
        "missing_files": missing_files or [],
        "invalid_fields": invalid_fields or [],
        "evidence_needed": evidence_needed or [],
        "source_verification_status": "NOT_VERIFIED",
        "scientific_review_status": "NOT_REVIEWED",
    }


def _status_for(
    rows: list[dict[str, str]],
    errors: list[str],
    path: Path,
    root: Path,
    *,
    evidence_needed: list[str],
    test_only: bool = False,
) -> dict[str, Any]:
    relative = str(path.relative_to(root))
    missing_errors = [error for error in errors if error.startswith("Missing file:")]
    if missing_errors:
        return _requirement(
            "MISSING",
            path=relative,
            details="Required source files are absent.",
            missing_files=missing_errors,
            evidence_needed=evidence_needed,
        )
    if errors:
        return _requirement(
            "INVALID",
            path=relative,
            details="One or more syntactic or consistency checks failed.",
            invalid_fields=errors,
            evidence_needed=evidence_needed,
        )
    if test_only or any(_contains_sentinel(row, TEST_SENTINELS) for row in rows):
        return _requirement(
            "UNVERIFIED",
            path=relative,
            details="Test-only or illustrative values are not source evidence.",
            evidence_needed=evidence_needed,
        )
    if any(_contains_sentinel(row, UNVERIFIED_SENTINELS) for row in rows):
        return _requirement(
            "UNVERIFIED",
            path=relative,
            details="Required declarations are present but include unknown or unverified values.",
            evidence_needed=evidence_needed,
        )
    return _requirement(
        "READY",
        path=relative,
        details=(
            "Required fields pass preflight syntax checks only. Source authority, permission, "
            "and any scientific approval remain unverified."
        ),
        evidence_needed=evidence_needed,
    )


def _read_required_csv(
    root: Path,
    relative: str,
    columns: tuple[str, ...],
    label: str,
) -> tuple[Path, list[dict[str, str]], list[str]]:
    path = root / relative
    if not path.is_file():
        return path, [], [f"Missing file: {relative}"]
    try:
        rows = _read_csv(path, columns, label)
    except (OSError, UnicodeError, csv.Error, ValueError) as error:
        return path, [], [str(error)]
    return path, rows, []


def _validate_mapping(rows: list[dict[str, str]]) -> list[str]:
    errors: list[str] = []
    gauge_ids: set[str] = set()
    site_keys: set[tuple[str, str, str, float, float]] = set()
    for index, row in enumerate(rows, start=2):
        prefix = f"nwdp_site_mapping.csv row {index}"
        gauge_id = row.get("gauge_id", "").strip()
        if not gauge_id:
            errors.append(f"{prefix}: gauge_id is empty.")
        elif gauge_id in gauge_ids:
            errors.append(f"{prefix}: duplicate gauge_id {gauge_id!r}.")
        gauge_ids.add(gauge_id)
        if row.get("mapping_status", "").strip().upper() != "APPROVED":
            errors.append(f"{prefix}: mapping_status must declare APPROVED.")
        for field in ("mapping_reference", "quality_mapping_reference"):
            if not row.get(field, "").strip():
                errors.append(f"{prefix}: {field} is empty.")
        datum = row.get("vertical_datum", "").strip().upper()
        quality = row.get("quality_flag", "").strip().upper()
        if datum in UNVERIFIED_SENTINELS:
            errors.append(f"{prefix}: vertical_datum is missing or unverified.")
        if quality not in {"VALID", "GOOD", "APPROVED"}:
            errors.append(f"{prefix}: quality_flag is not a supported verified flag.")
        try:
            site = (
                row["Station"].strip().casefold(),
                row["State LGD Code"].strip(),
                row["District LGD Code"].strip(),
                *_check_coordinates(row, "Latitude", "Longitude", "site mapping"),
            )
        except (KeyError, ValueError) as error:
            errors.append(f"{prefix}: {error}")
        else:
            if site in site_keys:
                errors.append(f"{prefix}: duplicate station identity and coordinates.")
            site_keys.add(site)
    return errors


def _validate_units_datums(
    observations: list[dict[str, str]],
    mapping_rows: list[dict[str, str]],
) -> list[str]:
    errors: list[str] = []
    datum_by_gauge = {
        row.get("gauge_id", "").strip(): row.get("vertical_datum", "").strip()
        for row in mapping_rows
    }
    for index, row in enumerate(observations, start=2):
        gauge_id = row.get("gauge_id", "").strip()
        datum = row.get("vertical_datum", "").strip()
        if not datum or datum.upper() in UNVERIFIED_SENTINELS:
            errors.append(f"gauge_water_level_observations.csv row {index}: vertical_datum is unverified.")
        elif datum_by_gauge.get(gauge_id) != datum:
            errors.append(
                f"gauge_water_level_observations.csv row {index}: vertical_datum does not match the gauge mapping."
            )
    return errors


def _validate_observation_danger_datums(
    observations_by_gauge: dict[str, list[dict[str, Any]]],
    danger_levels_by_gauge: dict[str, list[dict[str, Any]]],
) -> tuple[list[str], list[str]]:
    datum_errors: list[str] = []
    effective_level_errors: list[str] = []
    for gauge_id, observations in observations_by_gauge.items():
        danger_levels = danger_levels_by_gauge.get(gauge_id, [])
        for observation in observations:
            observed_at = observation["observed_at"]
            matching_levels = [
                level for level in danger_levels
                if level["effective_from"] <= observed_at < level["effective_to"]
            ]
            if not matching_levels:
                effective_level_errors.append(
                    f"Gauge {gauge_id!r} has no effective danger-level record at "
                    f"{observed_at.isoformat()}."
                )
                continue
            observation_datum = observation["vertical_datum"]
            if any(level["vertical_datum"] != observation_datum for level in matching_levels):
                datum_errors.append(
                    f"Gauge {gauge_id!r} observation datum does not match the effective "
                    f"danger-level datum at {observed_at.isoformat()}."
                )
    return datum_errors, effective_level_errors


def _validate_provenance(root: Path, source_meta_path: Path) -> tuple[dict[str, dict[str, str]] | None, list[str]]:
    if not source_meta_path.is_file():
        return None, [f"Missing file: {source_meta_path.relative_to(root)}"]
    try:
        metadata = _load_metadata(source_meta_path)
        raw_payload = json.loads(source_meta_path.read_text(encoding="utf-8"))
        raw_sources = raw_payload["sources"]
        for source in METADATA_SOURCES:
            metadata[source].update(
                {
                    key: str(value).strip()
                    for key, value in raw_sources[source].items()
                    if key not in metadata[source]
                }
            )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        return None, [str(error)]
    errors: list[str] = []
    for source in METADATA_SOURCES:
        entry = metadata[source]
        timezone_name = entry.get("source_timezone", "").strip()
        if not timezone_name or timezone_name.upper() in UNVERIFIED_SENTINELS:
            errors.append(f"source_metadata.{source}.source_timezone is missing or unverified.")
        else:
            try:
                ZoneInfo(timezone_name)
            except ZoneInfoNotFoundError:
                errors.append(f"source_metadata.{source}.source_timezone is not a valid IANA timezone.")
        if not entry.get("source_url", "").strip():
            errors.append(f"source_metadata.{source}.source_url is missing.")
        if not entry.get("field_mapping_reference", "").strip():
            errors.append(f"source_metadata.{source}.field_mapping_reference is missing.")
    if metadata["observations"].get("water_level_unit") != "m":
        errors.append("source_metadata.observations.water_level_unit must be 'm'.")

    observation_manifest = root / "ml" / "datasets" / "hydrological" / "raw" / (
        "gauge_water_level_observations.manifest.json"
    )
    expected_mapping = root / "ml" / "datasets" / "flood_training" / "nwdp_site_mapping.csv"
    expected_observations = (
        root / "ml" / "datasets" / "hydrological" / "raw" / "gauge_water_level_observations.csv"
    )
    source_metadata_observation = Path(metadata["observations"]["raw_source_file"]).resolve()
    declared_observation_hash = metadata["observations"]["raw_source_sha256"].lower()
    if not observation_manifest.is_file():
        errors.append(
            "Missing file: ml/datasets/hydrological/raw/gauge_water_level_observations.manifest.json"
        )
    else:
        try:
            manifest = json.loads(observation_manifest.read_text(encoding="utf-8"))
            output_path = Path(manifest["output_file"])
            mapping_path = Path(manifest["mapping_file"])
            source_path = Path(manifest["source_file"])
            if output_path.resolve() != expected_observations.resolve():
                errors.append("Normalization manifest output_file does not identify the canonical observations file.")
            if mapping_path.resolve() != expected_mapping.resolve():
                errors.append("Normalization manifest mapping_file does not identify nwdp_site_mapping.csv.")
            if source_path.resolve() != source_metadata_observation:
                errors.append(
                    "Normalization manifest raw source differs from source_metadata.observations.raw_source_file."
                )
            if sha256_file(output_path) != manifest["output_sha256"]:
                errors.append("Normalization manifest output SHA-256 does not match.")
            if sha256_file(mapping_path) != manifest["mapping_sha256"]:
                errors.append("Normalization manifest mapping SHA-256 does not match.")
            if sha256_file(source_path) != manifest["source_sha256"]:
                errors.append("Normalization manifest raw-source SHA-256 does not match.")
            if str(manifest["source_sha256"]).lower() != declared_observation_hash:
                errors.append(
                    "Normalization manifest raw-source hash differs from source_metadata.observations."
                )
            if manifest.get("source_timezone") != metadata["observations"]["source_timezone"]:
                errors.append("Normalization manifest timezone differs from source metadata.")
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            errors.append(f"Observation normalization manifest is invalid: {error}")
    return metadata, errors


def _validate_nwdp_resource_metadata(root: Path) -> list[str]:
    path = root / "ml" / "datasets" / "raw_sources" / "nwdp" / "resource_metadata.json"
    if not path.is_file():
        return [f"Missing file: {path.relative_to(root)}"]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        return [f"resource_metadata.json: {error}"]
    if not isinstance(payload, dict):
        return ["resource_metadata.json must contain a JSON object."]
    required_fields = ("resource_id", "source_url", "retrieved_at_utc")
    errors = [
        f"resource_metadata.{field} is missing."
        for field in required_fields
        if not str(payload.get(field, "")).strip()
    ]
    if payload.get("retrieved_at_utc"):
        try:
            _parse_timestamp(payload["retrieved_at_utc"], "resource_metadata.retrieved_at_utc")
        except ValueError as error:
            errors.append(str(error))
    return errors


def _validate_coverage_gaps(rows: list[dict[str, str]]) -> list[str]:
    errors: list[str] = []
    allowed_status = {"CONFIRMED_COMPLETE", "INCOMPLETE", "GAPS_DOCUMENTED"}
    for index, row in enumerate(rows, start=2):
        prefix = f"gauge_coverage_evidence.csv row {index}"
        status = row.get("complete_status", "").strip().upper()
        if status not in allowed_status:
            errors.append(f"{prefix}: complete_status must be one of {sorted(allowed_status)}.")
        if status in {"INCOMPLETE", "GAPS_DOCUMENTED"}:
            required_gap_fields = ("gap_start_utc", "gap_end_utc", "gap_reason")
            for field in required_gap_fields:
                if not row.get(field, "").strip():
                    errors.append(f"{prefix}: documented gap requires {field}.")
            if all(row.get(field, "").strip() for field in required_gap_fields):
                try:
                    gap_start = _parse_timestamp(row["gap_start_utc"], "gap_start_utc")
                    gap_end = _parse_timestamp(row["gap_end_utc"], "gap_end_utc")
                    window_start = _parse_timestamp(row["window_start_utc"], "window_start_utc")
                    window_end = _parse_timestamp(row["window_end_utc"], "window_end_utc")
                    if gap_start < window_start or gap_end > window_end or gap_end <= gap_start:
                        errors.append(f"{prefix}: documented gap is outside the coverage window.")
                except ValueError as error:
                    errors.append(f"{prefix}: {error}")
    return errors


def _validate_permissions(root: Path) -> list[str]:
    path = root / "ml" / "datasets" / "flood_training" / "licensing_evidence.json"
    if not path.is_file():
        return [f"Missing file: {path.relative_to(root)}"]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        return [f"licensing_evidence.json: {error}"]
    sources = payload.get("sources") if isinstance(payload, dict) else None
    if not isinstance(sources, dict):
        return ["licensing_evidence.json must contain a sources object."]
    required_fields = (
        "license_name",
        "evidence_reference",
        "applicable_uses",
        "redistribution_terms",
        "reviewer",
        "reviewed_at_utc",
    )
    errors = []
    for source in METADATA_SOURCES:
        entry = sources.get(source)
        if not isinstance(entry, dict):
            errors.append(f"licensing_evidence.sources.{source} is missing or invalid.")
            continue
        for field in required_fields:
            if not str(entry.get(field, "")).strip():
                errors.append(f"licensing_evidence.sources.{source}.{field} is missing.")
        if entry.get("reviewed_at_utc"):
            try:
                _parse_timestamp(entry["reviewed_at_utc"], f"{source}.reviewed_at_utc")
            except ValueError as error:
                errors.append(str(error))
    return errors


def _validate_weather_relevance(
    root: Path,
    crosswalk_rows: list[dict[str, str]],
) -> list[str]:
    archive_path = root / "ml" / "datasets" / "raw_sources" / "open_meteo" / "archive.json"
    manifest_path = archive_path.with_name("archive.manifest.json")
    errors: list[str] = []
    for path in (archive_path, manifest_path):
        if not path.is_file():
            errors.append(f"Missing file: {path.relative_to(root)}")
    if errors:
        return errors
    try:
        payload = json.loads(archive_path.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        requested = manifest["requested_location_wgs84"]
        _, _quality = build_predictor_frame(
            payload,
            requested_latitude=float(requested["latitude"]),
            requested_longitude=float(requested["longitude"]),
        )
        if sha256_file(archive_path) != manifest.get("retrieved_file_sha256"):
            errors.append("archive.manifest.json retrieved_file_sha256 does not match archive.json.")
        returned = manifest["returned_grid_location_wgs84"]
        if (
            float(returned["latitude"]) != float(payload["latitude"])
            or float(returned["longitude"]) != float(payload["longitude"])
        ):
            errors.append("Manifest returned grid coordinates do not match archive response.")
        expected_grid_id = (
            f"open-meteo-best-match:{float(payload['latitude']):.5f},"
            f"{float(payload['longitude']):.5f}"
        )
        matches = [
            row for row in crosswalk_rows
            if row.get("grid_location_id", "").strip() == expected_grid_id
        ]
        if not matches:
            errors.append(
                "No crosswalk grid_location_id matches the archive's provider-returned grid coordinates."
            )
        for row in matches:
            grid_lat, grid_lon = _check_coordinates(
                row, "grid_latitude", "grid_longitude", "crosswalk"
            )
            if (
                abs(grid_lat - float(payload["latitude"])) > 1e-4
                or abs(grid_lon - float(payload["longitude"])) > 1e-4
            ):
                errors.append("Crosswalk grid coordinates do not match the archive response.")
            if row.get("review_status", "").strip().upper() != "APPROVED":
                errors.append("Crosswalk does not declare approved weather relevance.")
            if not row.get("reference", "").strip() or not row.get("matching_method", "").strip():
                errors.append("Crosswalk must cite a review reference and matching method.")
        if _contains_sentinel(manifest, TEST_SENTINELS):
            errors.append("Weather archive manifest contains test-only or illustrative values.")
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        errors.append(f"Weather archive or manifest is invalid: {error}")
    return errors


def get_gauge_package_preflight(project_root: str | Path) -> dict[str, Any]:
    root = Path(project_root).resolve()
    mapping_path, mapping_rows, mapping_errors = _read_required_csv(
        root,
        "ml/datasets/flood_training/nwdp_site_mapping.csv",
        MAPPING_COLUMNS,
        "NWDP site mapping",
    )
    mapping_errors.extend(_validate_mapping(mapping_rows))

    observations_path, observations, observation_errors = _read_required_csv(
        root,
        "ml/datasets/hydrological/raw/gauge_water_level_observations.csv",
        OBSERVATION_COLUMNS,
        "gauge observations",
    )
    danger_path, dangers, danger_errors = _read_required_csv(
        root,
        "ml/datasets/hydrological/raw/official_gauge_danger_levels.csv",
        DANGER_LEVEL_COLUMNS,
        "official danger levels",
    )
    coverage_path, coverage, coverage_errors = _read_required_csv(
        root,
        "ml/datasets/flood_training/gauge_coverage_evidence.csv",
        COVERAGE_COLUMNS,
        "gauge coverage",
    )
    crosswalk_path, crosswalk, crosswalk_errors = _read_required_csv(
        root,
        "ml/datasets/flood_training/gauge_grid_crosswalk.csv",
        CROSSWALK_COLUMNS,
        "gauge/grid crosswalk",
    )

    metadata_path = root / "ml" / "datasets" / "flood_training" / "source_metadata.json"
    metadata, provenance_errors = _validate_provenance(root, metadata_path)
    provenance_errors.extend(_validate_nwdp_resource_metadata(root))
    observations_by_gauge = None
    danger_levels_by_gauge = None
    if observations and not observation_errors:
        try:
            source_timezone = (
                metadata["observations"]["source_timezone"] if metadata is not None else None
            )
            observations_by_gauge, _ = _validate_observations(observations, source_timezone)
        except (KeyError, TypeError, ValueError) as error:
            observation_errors.append(str(error))
    if dangers and not danger_errors:
        try:
            danger_levels_by_gauge = _validate_thresholds(dangers)
        except (KeyError, TypeError, ValueError) as error:
            danger_errors.append(str(error))
    if coverage and not coverage_errors:
        try:
            _validate_coverage(coverage)
        except (KeyError, TypeError, ValueError) as error:
            coverage_errors.append(str(error))
        coverage_errors.extend(_validate_coverage_gaps(coverage))
    if crosswalk and not crosswalk_errors:
        try:
            _validate_crosswalk(crosswalk)
        except (KeyError, TypeError, ValueError) as error:
            crosswalk_errors.append(str(error))

    unit_errors = _validate_units_datums(observations, mapping_rows)
    if observations_by_gauge is not None and danger_levels_by_gauge is not None:
        datum_errors, effective_level_errors = _validate_observation_danger_datums(
            observations_by_gauge,
            danger_levels_by_gauge,
        )
        unit_errors.extend(datum_errors)
        danger_errors.extend(datum_errors)
        danger_errors.extend(effective_level_errors)
    mapping_by_gauge = {
        row.get("gauge_id", "").strip(): row for row in mapping_rows
    }
    for index, row in enumerate(crosswalk, start=2):
        gauge_id = row.get("gauge_id", "").strip()
        mapped_site = mapping_by_gauge.get(gauge_id)
        if mapped_site is None:
            crosswalk_errors.append(
                f"gauge_grid_crosswalk.csv row {index}: gauge_id is absent from the official site mapping."
            )
            continue
        try:
            gauge_latitude, gauge_longitude = _check_coordinates(
                row, "gauge_latitude", "gauge_longitude", "crosswalk"
            )
            official_latitude, official_longitude = _check_coordinates(
                mapped_site, "Latitude", "Longitude", "site mapping"
            )
            if (
                gauge_latitude != official_latitude
                or gauge_longitude != official_longitude
            ):
                crosswalk_errors.append(
                    f"gauge_grid_crosswalk.csv row {index}: gauge coordinates differ from the mapped provider site."
                )
        except (KeyError, ValueError) as error:
            crosswalk_errors.append(f"gauge_grid_crosswalk.csv row {index}: {error}")
    mapped_gauges = set(mapping_by_gauge)
    for label, rows in (
        ("observations", observations),
        ("danger levels", dangers),
        ("coverage", coverage),
    ):
        for index, row in enumerate(rows, start=2):
            gauge_id = row.get("gauge_id", "").strip()
            if gauge_id and gauge_id not in mapped_gauges:
                if label == "observations":
                    observation_errors.append(
                        f"gauge_water_level_observations.csv row {index}: gauge_id is absent from the official site mapping."
                    )
                elif label == "danger levels":
                    danger_errors.append(
                        f"official_gauge_danger_levels.csv row {index}: gauge_id is absent from the official site mapping."
                    )
                else:
                    coverage_errors.append(
                        f"gauge_coverage_evidence.csv row {index}: gauge_id is absent from the official site mapping."
                    )
    permission_errors = _validate_permissions(root)
    weather_errors = _validate_weather_relevance(root, crosswalk)

    all_files = [
        mapping_path,
        observations_path,
        danger_path,
        coverage_path,
        crosswalk_path,
        metadata_path,
        root / "ml/datasets/raw_sources/nwdp/cwc_export.csv",
        root / "ml/datasets/raw_sources/nwdp/resource_metadata.json",
        root / "ml/datasets/flood_training/licensing_evidence.json",
        root / "ml/datasets/hydrological/raw/gauge_water_level_observations.manifest.json",
        root / "ml/datasets/raw_sources/open_meteo/archive.json",
        root / "ml/datasets/raw_sources/open_meteo/archive.manifest.json",
    ]
    missing_files = sorted(
        str(path.relative_to(root)) for path in all_files if not path.is_file()
    )
    test_only = any(
        _contains_sentinel(rows, TEST_SENTINELS)
        for rows in (mapping_rows, observations, dangers, coverage, crosswalk)
    )
    if metadata is not None and _contains_sentinel(metadata, TEST_SENTINELS):
        test_only = True
    for path in (
        root / "ml/datasets/flood_training/licensing_evidence.json",
        root / "ml/datasets/raw_sources/open_meteo/archive.manifest.json",
        root / "ml/datasets/raw_sources/nwdp/resource_metadata.json",
    ):
        if path.is_file():
            try:
                test_only = test_only or _contains_sentinel(
                    json.loads(path.read_text(encoding="utf-8")),
                    TEST_SENTINELS,
                )
            except (OSError, UnicodeError, json.JSONDecodeError):
                pass

    evidence_needed = {
        "gauge_identity_and_coordinates": [
            "Official gauge registry or provider document confirming stable gauge ID, station identity, and WGS 84 coordinates.",
        ],
        "water_level_units_and_vertical_datum": [
            "Provider data dictionary confirming metre units, gauge vertical datum, and quality-flag semantics.",
        ],
        "source_provenance_and_timestamp_timezone": [
            "Unchanged raw export, source/resource metadata, retrieval time, source timezone, field mapping, and matching verified hashes.",
        ],
        "effective_danger_levels": [
            "Official gauge danger-level records with source IDs, units, vertical datum, and valid effective intervals.",
        ],
        "monitoring_completeness_and_gaps": [
            "Provider/operator cadence and completeness evidence for every claimed interval; record each gap and reason.",
        ],
        "data_use_and_model_training_permissions": [
            "Applicable written license/permission evidence explicitly covering the intended model-training and redistribution uses.",
        ],
        "weather_gauge_or_catchment_relevance": [
            "Independent scientific review connecting the returned weather grid to the gauge/catchment; coordinate proximity alone is insufficient.",
        ],
    }
    coverage_requirement = _status_for(
        coverage,
        coverage_errors,
        coverage_path,
        root,
        evidence_needed=evidence_needed["monitoring_completeness_and_gaps"],
        test_only=test_only,
    )
    if (
        not coverage_errors
        and coverage
        and any(
            row.get("complete_status", "").strip().upper()
            != "CONFIRMED_COMPLETE"
            for row in coverage
        )
        and coverage_requirement["status"] == "READY"
    ):
        coverage_requirement["status"] = "UNVERIFIED"
        coverage_requirement["details"] = (
            "Coverage gaps are declared; these intervals cannot support verified negative windows."
        )

    requirements = {
        "gauge_identity_and_coordinates": _status_for(
            mapping_rows,
            mapping_errors,
            mapping_path,
            root,
            evidence_needed=evidence_needed["gauge_identity_and_coordinates"],
            test_only=test_only,
        ),
        "water_level_units_and_vertical_datum": _status_for(
            observations,
            observation_errors + danger_errors + unit_errors,
            observations_path,
            root,
            evidence_needed=evidence_needed["water_level_units_and_vertical_datum"],
            test_only=test_only,
        ),
        "source_provenance_and_timestamp_timezone": _status_for(
            [],
            provenance_errors,
            metadata_path,
            root,
            evidence_needed=evidence_needed["source_provenance_and_timestamp_timezone"],
            test_only=test_only,
        ),
        "effective_danger_levels": _status_for(
            dangers,
            danger_errors,
            danger_path,
            root,
            evidence_needed=evidence_needed["effective_danger_levels"],
            test_only=test_only,
        ),
        "monitoring_completeness_and_gaps": coverage_requirement,
        "data_use_and_model_training_permissions": _status_for(
            [],
            permission_errors,
            root / "ml/datasets/flood_training/licensing_evidence.json",
            root,
            evidence_needed=evidence_needed["data_use_and_model_training_permissions"],
            test_only=test_only,
        ),
        "weather_gauge_or_catchment_relevance": _status_for(
            crosswalk,
            crosswalk_errors + weather_errors,
            crosswalk_path,
            root,
            evidence_needed=evidence_needed["weather_gauge_or_catchment_relevance"],
            test_only=test_only,
        ),
    }
    if missing_files:
        for name, requirement in requirements.items():
            paths = [path for path in missing_files if requirement["path"] == path]
            if name == "source_provenance_and_timestamp_timezone":
                paths.extend(
                    path for path in missing_files if "source_metadata.json" in path
                    or "gauge_water_level_observations.manifest.json" in path
                    or "raw_sources" in path
                )
            elif name == "data_use_and_model_training_permissions":
                paths.extend(path for path in missing_files if "licensing_evidence.json" in path)
            elif name == "weather_gauge_or_catchment_relevance":
                paths.extend(
                    path for path in missing_files
                    if "raw_sources/open_meteo" in path
                )
            if paths and requirement["status"] != "INVALID":
                requirement["status"] = "MISSING"
                requirement["missing_files"] = sorted(set(paths))

    blocking = [name for name, item in requirements.items() if item["status"] != "READY"]
    return {
        "preflight_status": "READY_FOR_EXTERNAL_REVIEW" if not blocking else "BLOCKED",
        "training_readiness": "NOT_READY",
        "test_only_package_detected": test_only,
        "requirements": requirements,
        "missing_files": missing_files,
        "blocking_requirements": blocking,
        "evidence_boundary": (
            "READY means only that package structure and declared values passed local preflight. "
            "This tool cannot authenticate official sources, permission, provider completeness, "
            "or scientific review; prediction readiness remains NOT_READY."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Preflight a prospective gauge-data package without authenticating evidence or creating labels."
    )
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = get_gauge_package_preflight(args.root)
    serialized = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    print(serialized, end="")


if __name__ == "__main__":
    main()
