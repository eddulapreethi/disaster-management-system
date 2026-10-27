import csv
import json
from pathlib import Path

from ml.preprocessing.flood_target_readiness import get_flood_target_readiness
from ml.preprocessing.file_integrity import sha256_file


def test_target_readiness_lists_missing_evidence_and_never_promotes_file_presence(tmp_path: Path) -> None:
    readiness = get_flood_target_readiness(tmp_path)

    assert readiness["status"] == "NOT_READY"
    assert readiness["target_status"] == "PROPOSED_REQUIRES_DOMAIN_APPROVAL"
    assert readiness["missing_evidence"] == list(readiness["files"])
    assert readiness["gauge_package_preflight"]["training_readiness"] == "NOT_READY"
    assert readiness["gauge_package_preflight"]["preflight_status"] == "BLOCKED"

    for item in readiness["files"].values():
        path = tmp_path / item["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("test-only placeholder", encoding="utf-8")

    readiness_with_files = get_flood_target_readiness(tmp_path)

    assert readiness_with_files["missing_evidence"] == []
    assert readiness_with_files["status"] == "NOT_READY"
    assert readiness_with_files["target_status"] == "PROPOSED_REQUIRES_DOMAIN_APPROVAL"
    assert readiness_with_files["blocking_requirements"]
    assert readiness_with_files["gauge_package_preflight"]["training_readiness"] == "NOT_READY"
    assert all(
        item["source_verification_status"] != "VERIFIED"
        for item in readiness_with_files["requirements"].values()
    )
    assert readiness_with_files["requirements"]["official_danger_levels"]["status"] == "SYNTACTICALLY_INVALID"


def _write_csv(path: Path, headers: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=headers, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def test_readiness_reports_required_evidence_separately_and_keeps_all_unverified(
    tmp_path: Path,
) -> None:
    data = tmp_path / "ml" / "datasets"
    observations_path = data / "hydrological" / "raw" / "gauge_water_level_observations.csv"
    danger_path = data / "hydrological" / "raw" / "official_gauge_danger_levels.csv"
    coverage_path = data / "flood_training" / "gauge_coverage_evidence.csv"
    mapping_path = data / "flood_training" / "gauge_grid_crosswalk.csv"
    assessment_path = data / "flood_training" / "window_assessments.csv"
    weather_path = data / "raw_sources" / "open_meteo" / "archive.json"
    weather_manifest_path = data / "raw_sources" / "open_meteo" / "archive.manifest.json"
    license_path = data / "flood_training" / "licensing_evidence.json"
    metadata_path = data / "flood_training" / "source_metadata.json"

    _write_csv(
        observations_path,
        ["gauge_id", "observed_at", "water_level_m", "vertical_datum", "quality_flag"],
        [
            {
                "gauge_id": "gauge-a",
                "observed_at": "2025-01-01T00:00:00Z",
                "water_level_m": "1.0",
                "vertical_datum": "datum-A",
                "quality_flag": "UNVERIFIED",
            }
        ],
    )
    _write_csv(
        danger_path,
        [
            "gauge_id",
            "threshold_record_id",
            "effective_from",
            "effective_to",
            "danger_level_m",
            "vertical_datum",
            "unit",
        ],
        [
            {
                "gauge_id": "gauge-a",
                "threshold_record_id": "threshold-a",
                "effective_from": "2024-01-01T00:00:00Z",
                "effective_to": "2026-01-01T00:00:00Z",
                "danger_level_m": "5.0",
                "vertical_datum": "datum-B",
                "unit": "m",
            }
        ],
    )
    _write_csv(
        coverage_path,
        [
            "gauge_id",
            "window_start_utc",
            "window_end_utc",
            "expected_interval_minutes",
            "complete_status",
            "evidence_reference",
            "source_record_id",
        ],
        [
            {
                "gauge_id": "gauge-a",
                "window_start_utc": "2025-01-01T00:00:00Z",
                "window_end_utc": "2025-01-02T00:00:00Z",
                "expected_interval_minutes": 60,
                "complete_status": "CONFIRMED_COMPLETE",
                "evidence_reference": "provider-coverage-record",
                "source_record_id": "coverage-a",
            }
        ],
    )
    _write_csv(
        mapping_path,
        [
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
        ],
        [
            {
                "gauge_id": "gauge-a",
                "grid_location_id": "grid-a",
                "gauge_latitude": 20,
                "gauge_longitude": 80,
                "grid_latitude": 20,
                "grid_longitude": 80,
                "approved_max_distance_km": 0,
                "review_status": "APPROVED",
                "reviewer": "reviewer",
                "reviewed_at_utc": "2025-01-01T00:00:00Z",
                "reference": "review-ref",
                "matching_method": "catchment review",
            }
        ],
    )
    _write_csv(
        assessment_path,
        ["assessment", "gauge_id", "location_id", "prediction_issue_time_utc"],
        [
            {
                "assessment": "NEGATIVE_EVIDENCE_CHECKS_PASSED",
                "gauge_id": "gauge-a",
                "location_id": "grid-a",
                "prediction_issue_time_utc": "2025-01-01T00:00:00Z",
            }
        ],
    )
    weather_path.parent.mkdir(parents=True, exist_ok=True)
    weather_payload = {
        "latitude": 20.0,
        "longitude": 80.0,
        "timezone": "UTC",
        "utc_offset_seconds": 0,
        "daily_units": {
            "temperature_2m_mean": "°C",
            "precipitation_sum": "mm",
            "relative_humidity_2m_mean": "%",
            "wind_speed_10m_max": "km/h",
        },
        "daily": {
            "time": [f"2025-01-{day:02d}" for day in range(1, 9)],
            "temperature_2m_mean": [20.0] * 8,
            "precipitation_sum": [1.0] * 8,
            "relative_humidity_2m_mean": [60.0] * 8,
            "wind_speed_10m_max": [10.0] * 8,
        },
    }
    weather_path.write_text(json.dumps(weather_payload), encoding="utf-8")
    weather_manifest_path.write_text(
        json.dumps(
            {
                "requested_location_wgs84": {"latitude": 20.0, "longitude": 80.0},
                "returned_grid_location_wgs84": {"latitude": 20.0, "longitude": 80.0},
                "retrieved_file_sha256": sha256_file(weather_path),
            }
        ),
        encoding="utf-8",
    )
    license_path.parent.mkdir(parents=True, exist_ok=True)
    license_path.write_text(
        json.dumps(
            {
                "sources": {
                    name: {
                        "license_name": "declared-license",
                        "evidence_reference": "license-evidence-file",
                        "applicable_uses": "research",
                        "redistribution_terms": "requires independent review",
                        "reviewer": "reviewer",
                        "reviewed_at_utc": "2025-01-02T00:00:00Z",
                    }
                    for name in ("observations", "danger_levels", "crosswalk", "coverage", "predictors")
                }
            }
        ),
        encoding="utf-8",
    )
    metadata_path.write_text(
        json.dumps(
            {
                "sources": {
                    name: {
                        "license_status": "declared",
                        "license_reference": "declared-reference",
                        "license_evidence_reference": "license-evidence-file",
                    }
                    for name in ("observations", "danger_levels", "crosswalk", "coverage", "predictors")
                }
            }
        ),
        encoding="utf-8",
    )

    report = get_flood_target_readiness(tmp_path)
    requirements = report["requirements"]

    assert report["status"] == "NOT_READY"
    assert requirements["official_danger_levels"]["status"] == "SYNTACTICALLY_VALID_UNVERIFIED"
    assert requirements["matching_vertical_datums"]["status"] == "DECLARED_MISMATCH"
    assert requirements["complete_observation_coverage"]["status"] == "DECLARED_COMPLETE_UNVERIFIED"
    assert requirements["verified_negative_windows"]["status"] == "CANDIDATE_CHECKS_ONLY"
    assert requirements["reviewed_gauge_to_weather_mapping"]["status"] == "DECLARED_APPROVED_UNVERIFIED"
    assert requirements["historical_weather_coverage"]["status"] == "SYNTACTICALLY_VALID_UNVERIFIED"
    assert requirements["licensing_evidence"]["status"] == "PRESENT_UNVERIFIED"
    assert all(
        item["source_verification_status"] != "VERIFIED"
        for item in requirements.values()
    )
