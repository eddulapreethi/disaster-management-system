from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ml.preprocessing.flood_environmental_dataset import FEATURE_COLUMNS
from ml.preprocessing.file_integrity import sha256_file
from ml.preprocessing.flood_training_data_import import (
    assess_training_data_bundle,
    _parse_timestamp,
)

ISSUE = datetime(2025, 1, 1, tzinfo=timezone.utc)
END = ISSUE + timedelta(hours=24)


def _write_csv(path: Path, rows: list[dict[str, object]]) -> Path:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return path


def _bundle(tmp_path: Path) -> dict[str, Path]:
    observations = [
        {
            "gauge_id": "gauge-a",
            "source_record_id": f"obs-{index}",
            "observed_at": (ISSUE + timedelta(hours=index)).isoformat().replace("+00:00", "Z"),
            "water_level_m": 9.0,
            "vertical_datum": "CWC-gauge-datum-A",
            "quality_flag": "VALID",
        }
        for index in range(24)
    ]
    danger_levels = [
        {
            "gauge_id": "gauge-a",
            "threshold_record_id": "threshold-a",
            "effective_from": "2024-01-01T00:00:00Z",
            "effective_to": "2026-01-01T00:00:00Z",
            "danger_level_m": 10.0,
            "vertical_datum": "CWC-gauge-datum-A",
            "unit": "m",
        }
    ]
    crosswalk = [
        {
            "gauge_id": "gauge-a",
            "grid_location_id": "grid-a",
            "gauge_latitude": 20.0,
            "gauge_longitude": 80.0,
            "grid_latitude": 20.01,
            "grid_longitude": 80.01,
            "approved_max_distance_km": 5.0,
            "review_status": "APPROVED",
            "reviewer": "hydrologist",
            "reviewed_at_utc": "2024-01-01T00:00:00Z",
            "reference": "crosswalk-review-001",
            "matching_method": "reviewed catchment and grid-cell assessment",
        }
    ]
    coverage = [
        {
            "gauge_id": "gauge-a",
            "window_start_utc": ISSUE.isoformat().replace("+00:00", "Z"),
            "window_end_utc": END.isoformat().replace("+00:00", "Z"),
            "expected_interval_minutes": 60,
            "complete_status": "CONFIRMED_COMPLETE",
            "evidence_reference": "provider-coverage-log-001",
            "source_record_id": "coverage-001",
        }
    ]
    predictor = {
        "location_id": "grid-a",
        "grid_latitude": 20.01,
        "grid_longitude": 80.01,
        "prediction_issue_time_utc": ISSUE.isoformat().replace("+00:00", "Z"),
        "candidate_target_window_start_utc": ISSUE.isoformat().replace("+00:00", "Z"),
        "candidate_target_window_end_utc": END.isoformat().replace("+00:00", "Z"),
    }
    predictor.update({name: 1.0 for name in FEATURE_COLUMNS})
    metadata_sources = {}
    for name in ("observations", "danger_levels", "crosswalk", "coverage", "predictors"):
        raw_source = tmp_path / f"raw-{name}.csv"
        raw_source.write_text(f"unchanged source payload for {name}\n", encoding="utf-8")
        metadata_sources[name] = {
                "source_name": f"Reviewed source {name}",
                "source_url": f"https://example.test/{name}",
                "access_status": "DECLARED_BY_OPERATOR_REQUIRES_REVIEW",
                "license_status": "DECLARED_BY_OPERATOR_REQUIRES_REVIEW",
                "license_reference": "operator-supplied-reference",
                "license_evidence_reference": "license-evidence-file-pending-review",
                "retrieved_at_utc": "2025-01-02T00:00:00Z",
                "source_timezone": "UTC",
                "raw_source_file": raw_source.name,
                "raw_source_sha256": sha256_file(raw_source),
                "field_mapping_reference": f"mapping-review-{name}",
            }
    metadata = {"sources": metadata_sources}
    paths = {
        "observations": _write_csv(tmp_path / "observations.csv", observations),
        "danger_levels": _write_csv(tmp_path / "danger_levels.csv", danger_levels),
        "crosswalk": _write_csv(tmp_path / "crosswalk.csv", crosswalk),
        "coverage": _write_csv(tmp_path / "coverage.csv", coverage),
        "predictors": _write_csv(tmp_path / "predictors.csv", [predictor]),
    }
    metadata_path = tmp_path / "source_metadata.json"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    paths["source_metadata"] = metadata_path
    paths["output"] = tmp_path / "assessments.csv"
    return paths


def _assess(paths: dict[str, Path]) -> dict[str, object]:
    return assess_training_data_bundle(
        observations_path=paths["observations"],
        danger_levels_path=paths["danger_levels"],
        crosswalk_path=paths["crosswalk"],
        coverage_path=paths["coverage"],
        predictors_path=paths["predictors"],
        source_metadata_path=paths["source_metadata"],
        output_path=paths["output"],
    )


def _assessment(paths: dict[str, Path]) -> dict[str, str]:
    with paths["output"].open("r", encoding="utf-8", newline="") as stream:
        return next(csv.DictReader(stream))


def test_full_coverage_and_valid_below_threshold_passes_negative_evidence_checks(
    tmp_path: Path,
) -> None:
    paths = _bundle(tmp_path)
    original_bytes = (tmp_path / "raw-observations.csv").read_bytes()

    manifest = _assess(paths)

    assessment = _assessment(paths)
    assert assessment["assessment"] == "NEGATIVE_EVIDENCE_CHECKS_PASSED"
    assert "flood_occurrence" not in assessment
    assert assessment["expected_observation_count"] == "24"
    assert assessment["valid_observation_count"] == "24"
    assert manifest["status"] == "NOT_READY"
    assert manifest["input_files"]["observations"]["sha256"]
    assert manifest["input_files"]["observations"]["raw_source_sha256"] == sha256_file(
        tmp_path / "raw-observations.csv"
    )
    assert (tmp_path / "raw-observations.csv").read_bytes() == original_bytes
    assert paths["output"].with_suffix(".manifest.json").is_file()


def test_missing_measurement_or_unverified_coverage_cannot_be_a_negative(tmp_path: Path) -> None:
    paths = _bundle(tmp_path)
    observations = list(csv.DictReader(paths["observations"].open(encoding="utf-8")))
    _write_csv(paths["observations"], observations[:-1])

    _assess(paths)

    assert _assessment(paths)["assessment"] == "INDETERMINATE_INCOMPLETE_COVERAGE"
    assert "flood_occurrence" not in _assessment(paths)

    coverage = list(csv.DictReader(paths["coverage"].open(encoding="utf-8")))
    coverage[0]["complete_status"] = "UNVERIFIED"
    _write_csv(paths["coverage"], coverage)
    _assess(paths)
    assert _assessment(paths)["assessment"] == "INDETERMINATE_INCOMPLETE_COVERAGE"


def test_positive_measurement_can_be_identified_without_complete_coverage(tmp_path: Path) -> None:
    paths = _bundle(tmp_path)
    observations = list(csv.DictReader(paths["observations"].open(encoding="utf-8")))
    observations[4]["water_level_m"] = "10.0"
    _write_csv(paths["observations"], observations[:-1])

    _assess(paths)

    assert _assessment(paths)["assessment"] == "POSITIVE_EVIDENCE_CHECKS_PASSED"
    assert "flood_occurrence" not in _assessment(paths)


def test_invalid_measurement_quality_prevents_negative_label(tmp_path: Path) -> None:
    paths = _bundle(tmp_path)
    observations = list(csv.DictReader(paths["observations"].open(encoding="utf-8")))
    observations[3]["quality_flag"] = "SUSPECT"
    _write_csv(paths["observations"], observations)

    manifest = _assess(paths)

    assert _assessment(paths)["assessment"] == "INDETERMINATE_INCOMPLETE_COVERAGE"
    assert manifest["invalid_or_unusable_observations"] == 1


def test_duplicate_observation_timestamp_is_rejected(tmp_path: Path) -> None:
    paths = _bundle(tmp_path)
    observations = list(csv.DictReader(paths["observations"].open(encoding="utf-8")))
    observations.append(observations[0])
    _write_csv(paths["observations"], observations)

    with pytest.raises(ValueError, match="Duplicate observation"):
        _assess(paths)


def test_danger_level_must_cover_whole_window_and_intervals_must_not_overlap(
    tmp_path: Path,
) -> None:
    paths = _bundle(tmp_path)
    thresholds = list(csv.DictReader(paths["danger_levels"].open(encoding="utf-8")))
    thresholds[0]["effective_to"] = "2025-01-01T12:00:00Z"
    _write_csv(paths["danger_levels"], thresholds)
    _assess(paths)
    assert _assessment(paths)["assessment"] == "INDETERMINATE_DANGER_LEVEL"

    thresholds[0]["effective_to"] = "2026-01-01T00:00:00Z"
    thresholds.append(
        {
            **thresholds[0],
            "threshold_record_id": "overlap",
            "effective_from": "2025-01-01T00:00:00Z",
        }
    )
    _write_csv(paths["danger_levels"], thresholds)
    with pytest.raises(ValueError, match="intervals overlap"):
        _assess(paths)


def test_unknown_or_mismatched_vertical_datum_cannot_produce_a_label(tmp_path: Path) -> None:
    paths = _bundle(tmp_path)
    observations = list(csv.DictReader(paths["observations"].open(encoding="utf-8")))
    observations[0]["vertical_datum"] = "different-datum"
    _write_csv(paths["observations"], observations)
    _assess(paths)
    assert _assessment(paths)["assessment"] == "INDETERMINATE_VERTICAL_DATUM"

    observations[0]["vertical_datum"] = "UNKNOWN"
    _write_csv(paths["observations"], observations)
    with pytest.raises(ValueError, match="vertical datum is not established"):
        _assess(paths)


def test_incorrect_or_unreviewed_gauge_grid_mapping_is_not_labeled(tmp_path: Path) -> None:
    paths = _bundle(tmp_path)
    crosswalk = list(csv.DictReader(paths["crosswalk"].open(encoding="utf-8")))
    crosswalk[0]["grid_location_id"] = "different-grid"
    _write_csv(paths["crosswalk"], crosswalk)
    _assess(paths)
    assert _assessment(paths)["assessment"] == "INDETERMINATE_NO_REVIEWED_CROSSWALK"

    crosswalk[0]["grid_location_id"] = "grid-a"
    crosswalk[0]["review_status"] = "PROPOSED"
    _write_csv(paths["crosswalk"], crosswalk)
    with pytest.raises(ValueError, match="not explicitly approved"):
        _assess(paths)


def test_spatial_crosswalk_must_meet_its_reviewed_distance_limit(tmp_path: Path) -> None:
    paths = _bundle(tmp_path)
    crosswalk = list(csv.DictReader(paths["crosswalk"].open(encoding="utf-8")))
    crosswalk[0]["approved_max_distance_km"] = "0.01"
    _write_csv(paths["crosswalk"], crosswalk)

    with pytest.raises(ValueError, match="exceeding the reviewed limit"):
        _assess(paths)


def test_predictor_grid_coordinates_and_24_hour_window_must_match_mapping(tmp_path: Path) -> None:
    paths = _bundle(tmp_path)
    predictor = list(csv.DictReader(paths["predictors"].open(encoding="utf-8")))
    predictor[0]["grid_latitude"] = "20.5"
    _write_csv(paths["predictors"], predictor)
    _assess(paths)
    assert _assessment(paths)["assessment"] == "INDETERMINATE_GAUGE_GRID_MISMATCH"

    predictor[0]["grid_latitude"] = "20.01"
    predictor[0]["candidate_target_window_end_utc"] = "2025-01-02T01:00:00Z"
    _write_csv(paths["predictors"], predictor)
    with pytest.raises(ValueError, match="half-open 24-hour UTC window"):
        _assess(paths)


def test_naive_observation_times_require_explicit_source_timezone() -> None:
    with pytest.raises(ValueError, match="timezone-naive"):
        _parse_timestamp("01-01-2025 05:30", "observed_at")

    parsed = _parse_timestamp("01-01-2025 05:30", "observed_at", "Asia/Kolkata")

    assert parsed == ISSUE


def test_source_manifest_requires_original_file_hash_and_mapping_provenance(
    tmp_path: Path,
) -> None:
    paths = _bundle(tmp_path)
    metadata = json.loads(paths["source_metadata"].read_text(encoding="utf-8"))
    metadata["sources"]["observations"]["raw_source_sha256"] = "not-a-hash"
    paths["source_metadata"].write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(ValueError, match="64-character hexadecimal SHA-256"):
        _assess(paths)

    metadata["sources"]["observations"]["raw_source_sha256"] = "0" * 64
    paths["source_metadata"].write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(ValueError, match="does not match"):
        _assess(paths)


def test_cli_timezone_must_match_source_metadata_timezone(tmp_path: Path) -> None:
    paths = _bundle(tmp_path)

    with pytest.raises(ValueError, match="must match the observation source metadata"):
        assess_training_data_bundle(
            observations_path=paths["observations"],
            danger_levels_path=paths["danger_levels"],
            crosswalk_path=paths["crosswalk"],
            coverage_path=paths["coverage"],
            predictors_path=paths["predictors"],
            source_metadata_path=paths["source_metadata"],
            output_path=paths["output"],
            observation_timezone="Asia/Kolkata",
        )
