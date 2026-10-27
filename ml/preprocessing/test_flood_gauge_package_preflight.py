from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from ml.preprocessing.flood_gauge_package_preflight import (
    get_gauge_package_preflight,
)
from ml.preprocessing.flood_training_data_import import (
    CROSSWALK_COLUMNS,
    COVERAGE_COLUMNS,
    DANGER_LEVEL_COLUMNS,
    OBSERVATION_COLUMNS,
)
from ml.preprocessing.normalize_nwdp_observations import MAPPING_COLUMNS


def _write_csv(path: Path, columns: tuple[str, ...], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_complete_test_package(root: Path, *, test_only: bool = False) -> dict[str, Path]:
    mapping_path = root / "ml/datasets/flood_training/nwdp_site_mapping.csv"
    observation_path = root / "ml/datasets/hydrological/raw/gauge_water_level_observations.csv"
    danger_path = root / "ml/datasets/hydrological/raw/official_gauge_danger_levels.csv"
    coverage_path = root / "ml/datasets/flood_training/gauge_coverage_evidence.csv"
    crosswalk_path = root / "ml/datasets/flood_training/gauge_grid_crosswalk.csv"
    metadata_path = root / "ml/datasets/flood_training/source_metadata.json"
    license_path = root / "ml/datasets/flood_training/licensing_evidence.json"
    observation_manifest_path = observation_path.with_suffix(".manifest.json")
    archive_path = root / "ml/datasets/raw_sources/open_meteo/archive.json"
    archive_manifest_path = archive_path.with_name("archive.manifest.json")

    mapping_row = {
        "Station": "Example Station",
        "State LGD Code": "10",
        "District LGD Code": "101",
        "Latitude": "20.0",
        "Longitude": "80.0",
        "gauge_id": "OFFICIAL-GAUGE-1",
        "vertical_datum": "ProviderDatumA",
        "quality_flag": "VALID",
        "mapping_status": "APPROVED",
        "mapping_reference": "provider-registry-record",
        "quality_mapping_reference": "provider-data-dictionary",
    }
    if test_only:
        mapping_row["mapping_reference"] = "TEST_ONLY_registry_fixture"
    _write_csv(mapping_path, MAPPING_COLUMNS, [mapping_row])

    observation_rows = [
        {
            "gauge_id": "OFFICIAL-GAUGE-1",
            "source_record_id": f"obs-{index}",
            "observed_at": f"2025-01-01T{index:02d}:00:00Z",
            "water_level_m": "1.25",
            "vertical_datum": "ProviderDatumA",
            "quality_flag": "VALID",
        }
        for index in range(24)
    ]
    _write_csv(observation_path, OBSERVATION_COLUMNS, observation_rows)
    _write_csv(
        danger_path,
        DANGER_LEVEL_COLUMNS,
        [
            {
                "gauge_id": "OFFICIAL-GAUGE-1",
                "threshold_record_id": "official-threshold-1",
                "effective_from": "2024-01-01T00:00:00Z",
                "effective_to": "2026-01-01T00:00:00Z",
                "danger_level_m": "5.0",
                "vertical_datum": "ProviderDatumA",
                "unit": "m",
            }
        ],
    )
    coverage_row = {
        "gauge_id": "OFFICIAL-GAUGE-1",
        "window_start_utc": "2025-01-01T00:00:00Z",
        "window_end_utc": "2025-01-02T00:00:00Z",
        "expected_interval_minutes": "60",
        "complete_status": "CONFIRMED_COMPLETE",
        "evidence_reference": "provider-completeness-record",
        "source_record_id": "coverage-1",
    }
    _write_csv(coverage_path, COVERAGE_COLUMNS, [coverage_row])

    grid_id = "open-meteo-best-match:20.05000,80.05000"
    crosswalk_row = {
        "gauge_id": "OFFICIAL-GAUGE-1",
        "grid_location_id": grid_id,
        "gauge_latitude": "20.0",
        "gauge_longitude": "80.0",
        "grid_latitude": "20.05",
        "grid_longitude": "80.05",
        "approved_max_distance_km": "10.0",
        "review_status": "APPROVED",
        "reviewer": "qualified-reviewer",
        "reviewed_at_utc": "2025-01-03T00:00:00Z",
        "reference": "catchment-review-record",
        "matching_method": "documented catchment assessment",
    }
    _write_csv(crosswalk_path, CROSSWALK_COLUMNS, [crosswalk_row])

    source_entries = {}
    for source in ("observations", "danger_levels", "crosswalk", "coverage", "predictors"):
        raw_path = root / "ml/datasets/raw_sources/test" / f"{source}.csv"
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(f"test source artifact for {source}\n", encoding="utf-8")
        entry = {
            "source_name": f"Test fixture {source}",
            "source_url": f"https://example.invalid/{source}",
            "access_status": "TEST_ONLY" if test_only else "declared",
            "license_status": "TEST_ONLY" if test_only else "declared",
            "license_reference": "TEST_ONLY" if test_only else "declared-license-record",
            "license_evidence_reference": "TEST_ONLY" if test_only else "license-evidence-record",
            "retrieved_at_utc": "2025-01-03T01:00:00Z",
            "source_timezone": "UTC",
            "raw_source_file": str(raw_path.resolve()),
            "raw_source_sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
            "field_mapping_reference": "TEST_ONLY" if test_only else "reviewed-field-map",
        }
        if source == "observations":
            entry["water_level_unit"] = "m"
        source_entries[source] = entry
    _write_json(metadata_path, {"sources": source_entries})

    licensing_entries = {}
    for source in source_entries:
        licensing_entries[source] = {
            "license_name": "TEST_ONLY" if test_only else "declared-provider-license",
            "evidence_reference": "TEST_ONLY" if test_only else "license-evidence-record",
            "applicable_uses": "TEST_ONLY" if test_only else "research and model training",
            "redistribution_terms": "TEST_ONLY" if test_only else "requires external review",
            "reviewer": "TEST_ONLY" if test_only else "reviewer",
            "reviewed_at_utc": "2025-01-04T00:00:00Z",
        }
    _write_json(license_path, {"sources": licensing_entries})

    raw_nwdp = root / "ml/datasets/raw_sources/nwdp/cwc_export.csv"
    raw_mapping = mapping_path
    raw_nwdp.parent.mkdir(parents=True, exist_ok=True)
    raw_nwdp.write_text("test-only raw export\n", encoding="utf-8")
    source_entries["observations"]["raw_source_file"] = str(raw_nwdp.resolve())
    source_entries["observations"]["raw_source_sha256"] = hashlib.sha256(
        raw_nwdp.read_bytes()
    ).hexdigest()
    _write_json(metadata_path, {"sources": source_entries})
    _write_json(
        root / "ml/datasets/raw_sources/nwdp/resource_metadata.json",
        {
            "resource_id": "TEST_ONLY" if test_only else "resource-fixture-id",
            "source_url": "TEST_ONLY" if test_only else "https://example.invalid/nwdp-resource",
            "retrieved_at_utc": "2025-01-03T00:00:00Z",
        },
    )
    observation_manifest = {
        "source_file": str(raw_nwdp.resolve()),
        "source_sha256": hashlib.sha256(raw_nwdp.read_bytes()).hexdigest(),
        "mapping_file": str(raw_mapping.resolve()),
        "mapping_sha256": hashlib.sha256(raw_mapping.read_bytes()).hexdigest(),
        "source_timezone": "UTC",
        "output_file": str(observation_path.resolve()),
        "output_sha256": hashlib.sha256(observation_path.read_bytes()).hexdigest(),
        "row_count": len(observation_rows),
    }
    _write_json(observation_manifest_path, observation_manifest)

    archive_payload = {
        "latitude": 20.05,
        "longitude": 80.05,
        "timezone": "UTC",
        "utc_offset_seconds": 0,
        "daily_units": {
            "temperature_2m_mean": "°C",
            "precipitation_sum": "mm",
            "rain_sum": "mm",
            "wind_speed_10m_max": "km/h",
            "relative_humidity_2m_mean": "%",
        },
        "daily": {
            "time": [f"2025-01-{day:02d}" for day in range(1, 11)],
            "temperature_2m_mean": [20.0] * 10,
            "precipitation_sum": [1.0] * 10,
            "rain_sum": [1.0] * 10,
            "wind_speed_10m_max": [10.0] * 10,
            "relative_humidity_2m_mean": [60.0] * 10,
        },
    }
    _write_json(archive_path, archive_payload)
    _write_json(
        archive_manifest_path,
        {
            "requested_location_wgs84": {"latitude": 20.0, "longitude": 80.0},
            "returned_grid_location_wgs84": {"latitude": 20.05, "longitude": 80.05},
            "retrieved_file_sha256": hashlib.sha256(archive_path.read_bytes()).hexdigest(),
        },
    )
    return {
        "mapping": mapping_path,
        "observations": observation_path,
        "danger": danger_path,
        "coverage": coverage_path,
        "crosswalk": crosswalk_path,
        "metadata": metadata_path,
        "license": license_path,
        "archive": archive_path,
    }


def test_missing_package_files_are_reported_separately_and_never_ready(tmp_path: Path) -> None:
    report = get_gauge_package_preflight(tmp_path)

    assert report["preflight_status"] == "BLOCKED"
    assert report["training_readiness"] == "NOT_READY"
    assert report["missing_files"]
    assert report["requirements"]["gauge_identity_and_coordinates"]["status"] == "MISSING"
    assert report["requirements"]["effective_danger_levels"]["status"] == "MISSING"
    assert report["requirements"]["weather_gauge_or_catchment_relevance"]["status"] == "MISSING"


def test_illustrative_template_rows_never_count_as_official_evidence(tmp_path: Path) -> None:
    template = (
        Path(__file__).parent / "templates" / "nwdp_site_mapping_illustrative.csv"
    )
    target = tmp_path / "ml/datasets/flood_training/nwdp_site_mapping.csv"
    target.parent.mkdir(parents=True)
    target.write_bytes(template.read_bytes())

    report = get_gauge_package_preflight(tmp_path)

    assert report["requirements"]["gauge_identity_and_coordinates"]["status"] in {
        "INVALID",
        "UNVERIFIED",
    }
    assert report["training_readiness"] == "NOT_READY"


@pytest.mark.parametrize(
    ("file_key", "column", "value", "requirement"),
    [
        ("danger", "unit", "ft", "effective_danger_levels"),
        ("danger", "effective_to", "not-a-date", "effective_danger_levels"),
        ("mapping", "Latitude", "95", "gauge_identity_and_coordinates"),
        ("crosswalk", "gauge_longitude", "190", "weather_gauge_or_catchment_relevance"),
    ],
)
def test_invalid_units_dates_and_coordinates_are_reported(
    tmp_path: Path,
    file_key: str,
    column: str,
    value: str,
    requirement: str,
) -> None:
    paths = _write_complete_test_package(tmp_path)
    path = paths[file_key]
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        columns = reader.fieldnames
        rows = list(reader)
    rows[0][column] = value
    _write_csv(path, tuple(columns), rows)

    report = get_gauge_package_preflight(tmp_path)

    assert report["requirements"][requirement]["status"] == "INVALID"
    assert report["requirements"][requirement]["invalid_fields"]
    assert report["training_readiness"] == "NOT_READY"


def test_observation_datum_must_match_effective_danger_level_datum(tmp_path: Path) -> None:
    paths = _write_complete_test_package(tmp_path)
    with paths["danger"].open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        columns = reader.fieldnames
        rows = list(reader)
    rows[0]["vertical_datum"] = "DifferentProviderDatum"
    _write_csv(paths["danger"], tuple(columns), rows)

    report = get_gauge_package_preflight(tmp_path)

    assert report["requirements"]["water_level_units_and_vertical_datum"]["status"] == "INVALID"
    assert report["requirements"]["effective_danger_levels"]["status"] == "INVALID"
    assert report["training_readiness"] == "NOT_READY"


def test_each_observation_requires_an_effective_danger_level(tmp_path: Path) -> None:
    paths = _write_complete_test_package(tmp_path)
    with paths["danger"].open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        columns = reader.fieldnames
        rows = list(reader)
    rows[0]["effective_to"] = "2024-12-31T23:59:59Z"
    _write_csv(paths["danger"], tuple(columns), rows)

    report = get_gauge_package_preflight(tmp_path)

    danger_levels = report["requirements"]["effective_danger_levels"]
    assert danger_levels["status"] == "INVALID"
    assert any("no effective danger-level record" in field for field in danger_levels["invalid_fields"])
    assert report["training_readiness"] == "NOT_READY"


def test_incomplete_provenance_is_invalid_and_names_missing_fields(tmp_path: Path) -> None:
    paths = _write_complete_test_package(tmp_path)
    payload = json.loads(paths["metadata"].read_text(encoding="utf-8"))
    del payload["sources"]["observations"]["source_timezone"]
    _write_json(paths["metadata"], payload)

    report = get_gauge_package_preflight(tmp_path)
    provenance = report["requirements"]["source_provenance_and_timestamp_timezone"]

    assert provenance["status"] == "INVALID"
    assert any("source_timezone" in field for field in provenance["invalid_fields"])
    assert provenance["evidence_needed"]


def test_incomplete_coverage_requires_specific_gap_evidence(tmp_path: Path) -> None:
    paths = _write_complete_test_package(tmp_path)
    _write_csv(
        paths["coverage"],
        (*COVERAGE_COLUMNS, "gap_start_utc", "gap_end_utc", "gap_reason"),
        [
            {
                "gauge_id": "OFFICIAL-GAUGE-1",
                "window_start_utc": "2025-01-01T00:00:00Z",
                "window_end_utc": "2025-01-02T00:00:00Z",
                "expected_interval_minutes": "60",
                "complete_status": "GAPS_DOCUMENTED",
                "evidence_reference": "provider-completeness-record",
                "source_record_id": "coverage-1",
                "gap_start_utc": "2025-01-01T04:00:00Z",
                "gap_end_utc": "",
                "gap_reason": "provider outage",
            }
        ],
    )

    report = get_gauge_package_preflight(tmp_path)
    coverage = report["requirements"]["monitoring_completeness_and_gaps"]

    assert coverage["status"] == "INVALID"
    assert any("gap_end_utc" in field for field in coverage["invalid_fields"])
    assert report["training_readiness"] == "NOT_READY"


def test_documented_monitoring_gap_is_not_ready_for_negative_windows(tmp_path: Path) -> None:
    paths = _write_complete_test_package(tmp_path)
    _write_csv(
        paths["coverage"],
        (*COVERAGE_COLUMNS, "gap_start_utc", "gap_end_utc", "gap_reason"),
        [
            {
                "gauge_id": "OFFICIAL-GAUGE-1",
                "window_start_utc": "2025-01-01T00:00:00Z",
                "window_end_utc": "2025-01-02T00:00:00Z",
                "expected_interval_minutes": "60",
                "complete_status": "GAPS_DOCUMENTED",
                "evidence_reference": "provider-completeness-record",
                "source_record_id": "coverage-1",
                "gap_start_utc": "2025-01-01T04:00:00Z",
                "gap_end_utc": "2025-01-01T06:00:00Z",
                "gap_reason": "provider outage",
            }
        ],
    )

    report = get_gauge_package_preflight(tmp_path)
    coverage = report["requirements"]["monitoring_completeness_and_gaps"]

    assert coverage["status"] == "UNVERIFIED"
    assert "gaps are declared" in coverage["details"]
    assert report["training_readiness"] == "NOT_READY"


def test_missing_model_training_permission_is_reported(tmp_path: Path) -> None:
    paths = _write_complete_test_package(tmp_path)
    payload = json.loads(paths["license"].read_text(encoding="utf-8"))
    del payload["sources"]["predictors"]["applicable_uses"]
    _write_json(paths["license"], payload)

    report = get_gauge_package_preflight(tmp_path)
    permission = report["requirements"]["data_use_and_model_training_permissions"]

    assert permission["status"] == "INVALID"
    assert any("applicable_uses" in field for field in permission["invalid_fields"])
    assert report["training_readiness"] == "NOT_READY"


def test_fully_populated_test_only_package_is_unverified_and_does_not_promote_readiness(
    tmp_path: Path,
) -> None:
    _write_complete_test_package(tmp_path, test_only=True)

    report = get_gauge_package_preflight(tmp_path)

    assert report["test_only_package_detected"] is True
    assert report["preflight_status"] == "BLOCKED"
    assert report["training_readiness"] == "NOT_READY"
    assert all(
        requirement["status"] != "READY"
        for requirement in report["requirements"].values()
    )
    assert all(
        requirement["source_verification_status"] == "NOT_VERIFIED"
        for requirement in report["requirements"].values()
    )


def test_complete_declarations_are_only_preflight_ready_and_never_training_ready(
    tmp_path: Path,
) -> None:
    _write_complete_test_package(tmp_path)

    report = get_gauge_package_preflight(tmp_path)

    assert report["preflight_status"] == "READY_FOR_EXTERNAL_REVIEW"
    assert report["training_readiness"] == "NOT_READY"
    assert all(
        requirement["status"] == "READY"
        for requirement in report["requirements"].values()
    )
    assert all(
        requirement["source_verification_status"] == "NOT_VERIFIED"
        for requirement in report["requirements"].values()
    )
