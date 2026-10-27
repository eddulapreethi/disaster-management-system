from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import struct

from ml.preprocessing.hydraulic_model_preflight import (
    REQUIRED_INPUTS,
    validate_model_configuration,
)


ROOT = Path(__file__).resolve().parents[2]


def _write_csv(path: Path, columns: list[str], rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(columns)
        writer.writerows(rows)


def _write_geotiff(path: Path) -> None:
    entries: list[tuple[int, int, int, int]] = []
    entry_count = 11
    data_offset = 8 + 2 + entry_count * 12 + 4
    scale_offset = data_offset
    tiepoint_offset = scale_offset + 24
    geokey_offset = tiepoint_offset + 48
    pixel_offset = geokey_offset + 16

    def short_value(value: int) -> int:
        return struct.unpack("<I", struct.pack("<H", value) + b"\x00\x00")[0]

    entries.extend([
        (256, 4, 1, 1),
        (257, 4, 1, 1),
        (258, 3, 1, short_value(8)),
        (259, 3, 1, short_value(1)),
        (262, 3, 1, short_value(1)),
        (273, 4, 1, pixel_offset),
        (277, 3, 1, short_value(1)),
        (278, 4, 1, 1),
        (279, 4, 1, 1),
        (33550, 12, 3, scale_offset),
        (33922, 12, 6, tiepoint_offset),
        (34735, 3, 8, geokey_offset),
    ])
    entry_count = len(entries)
    data_offset = 8 + 2 + entry_count * 12 + 4
    scale_offset = data_offset
    tiepoint_offset = scale_offset + 24
    geokey_offset = tiepoint_offset + 48
    pixel_offset = geokey_offset + 16
    entries[5] = (273, 4, 1, pixel_offset)
    entries[9] = (33550, 12, 3, scale_offset)
    entries[10] = (33922, 12, 6, tiepoint_offset)
    entries[11] = (34735, 3, 8, geokey_offset)

    payload = bytearray(b"II*\x00" + struct.pack("<I", 8))
    payload.extend(struct.pack("<H", len(entries)))
    for entry in entries:
        payload.extend(struct.pack("<HHII", *entry))
    payload.extend(struct.pack("<I", 0))
    payload.extend(struct.pack("<3d", 30, 30, 0))
    payload.extend(struct.pack("<6d", 0, 0, 0, 76, 10, 0))
    payload.extend(struct.pack("<8H", 1, 1, 0, 1, 3072, 0, 1, 32643))
    payload.extend(b"\x00")
    path.write_bytes(payload)


def _complete_configuration(root: Path) -> dict:
    input_config: dict[str, dict] = {}
    for name in REQUIRED_INPUTS:
        path = root / "inputs" / f"{name}.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        if name == "terrain":
            path = path.with_suffix(".tif")
            _write_geotiff(path)
            file_format = "GeoTIFF"
            columns: list[str] = []
            units = {"vertical": "m"}
        elif name == "initial_conditions":
            path = path.with_suffix(".json")
            path.write_text('{"initial_state":"declared"}', encoding="utf-8")
            file_format = "JSON"
            columns = []
            units = {"vertical": "m"}
        else:
            file_format = "CSV"
            if name in {
                "water_level_observations",
                "rainfall_forcing",
                "upstream_boundary_conditions",
                "downstream_boundary_conditions",
                "calibration_observations",
                "validation_observations",
            }:
                columns = ["timestamp", "value"]
                if name in {"calibration_observations", "validation_observations"}:
                    columns.append("event_id")
                rows = [
                    [
                        "2025-01-01T00:00:00Z",
                        "1.0",
                        f"{name}-event",
                    ][: len(columns)],
                    [
                        "2025-01-01T01:00:00Z",
                        "2.0",
                        f"{name}-event",
                    ][: len(columns)],
                ]
            elif name == "channel_geometry":
                columns = ["section_id", "station", "elevation"]
                rows = [["fixture-section", "0", "1.0"]]
            elif name == "gauge_metadata":
                columns = ["gauge_id", "latitude", "longitude"]
                rows = [["fixture-only", "9.95", "76.25"]]
            elif name == "official_danger_levels":
                columns = ["gauge_id", "value", "effective_from", "effective_to"]
                rows = [[
                    "fixture-only",
                    "1.0",
                    "2025-01-01T00:00:00Z",
                    "2026-01-01T00:00:00Z",
                ]]
            else:
                columns = ["value"]
                rows = [["1.0"]]
            _write_csv(path, columns, rows)
            units = {"vertical": "m"}
            if name == "rainfall_forcing":
                units = {"rainfall": "mm/hour"}

        input_config[name] = {
            "path": str(path.relative_to(root)),
            "format": file_format,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "source_name": "test fixture only",
            "source_id": "fixture",
            "source_url": "https://example.invalid/fixture",
            "retrieved_at_utc": "2025-01-01T00:00:00Z",
            "crs": (
                "EPSG:4326"
                if name == "gauge_metadata"
                else "EPSG:32643"
                if name in {"terrain", "channel_geometry", "rainfall_forcing"}
                else "NOT_APPLICABLE"
            ),
            "units": units,
            "vertical_datum": (
                "FIXTURE_DATUM"
                if name in {
                    "terrain",
                    "channel_geometry",
                    "gauge_metadata",
                    "water_level_observations",
                    "official_danger_levels",
                }
                else None
            ),
            "coverage_bounds_wgs84": (
                [76.0, 9.8, 76.5, 10.1]
                if name in {"terrain", "channel_geometry", "gauge_metadata", "rainfall_forcing"}
                else None
            ),
            "required_columns": columns if file_format == "CSV" else None,
            "coordinate_columns": (
                {"latitude": "latitude", "longitude": "longitude"}
                if name == "gauge_metadata"
                else None
            ),
            "interval_columns": (
                ["effective_from", "effective_to"]
                if name == "official_danger_levels"
                else None
            ),
            "event_id_column": (
                "event_id"
                if name in {"calibration_observations", "validation_observations"}
                else None
            ),
            "timestamp_column": (
                "timestamp"
                if name in {
                    "water_level_observations",
                    "rainfall_forcing",
                    "upstream_boundary_conditions",
                    "downstream_boundary_conditions",
                    "calibration_observations",
                    "validation_observations",
                }
                else None
            ),
            "resolution": [30, 30] if name == "terrain" else None,
        }

    return {
        "configuration_version": "1.0",
        "execution_enabled": False,
        "model": {
            "name": "Fixture solver",
            "version": "0",
            "solver_family": "OTHER",
            "horizontal_crs": "EPSG:32643",
            "vertical_datum": "FIXTURE_DATUM",
            "units": {
                "horizontal": "m",
                "vertical": "m",
                "flow": "m3/s",
                "rainfall": "mm/hour",
            },
        },
        "study_area": {
            "name": "fixture area",
            "crs": "EPSG:4326",
            "bounds_wgs84": [76.0, 9.8, 76.5, 10.1],
        },
        "time_window": {
            "start_utc": "2025-01-01T00:00:00Z",
            "end_utc": "2025-01-02T00:00:00Z",
            "time_step_seconds": 60,
        },
        "inputs": input_config,
        "output_directory": "runs/fixture",
    }


def test_template_is_incomplete_and_never_authorizes_execution() -> None:
    template = json.loads(
        (ROOT / "ml" / "configs" / "hydraulic_model_config.template.json").read_text(
            encoding="utf-8"
        )
    )

    result = validate_model_configuration(template, ROOT)

    assert result["technical_status"] == "MISSING"
    assert result["execution_status"] == "NOT_READY"
    assert result["execution_permitted"] is False
    assert "model.solver_family" in result["missing_fields"]
    assert all(
        item["technical_status"] == "MISSING"
        for item in result["inputs"].values()
    )


def test_complete_technical_fixture_is_ready_but_not_approved_or_executable(
    tmp_path: Path,
) -> None:
    configuration = _complete_configuration(tmp_path)

    result = validate_model_configuration(configuration, tmp_path)

    assert result["technical_status"] == "READY"
    assert result["execution_status"] == "NOT_READY"
    assert result["execution_permitted"] is False
    assert all(
        item["technical_status"] == "READY" for item in result["inputs"].values()
    )
    assert all(
        status == "UNVERIFIED" for status in result["review_statuses"].values()
    )


def test_review_references_do_not_promote_source_or_scientific_approval(
    tmp_path: Path,
) -> None:
    configuration = _complete_configuration(tmp_path)
    configuration["inputs"]["terrain"]["review_evidence"] = {
        "source_authenticity": "review-ticket",
        "licensing": "license-document",
        "domain_approval": "approval-record",
        "scientific_suitability": "review-record",
    }

    result = validate_model_configuration(configuration, tmp_path)

    assert result["inputs"]["terrain"]["reviews"] == {
        "source_authenticity": "UNVERIFIED",
        "licensing": "UNVERIFIED",
        "domain_approval": "UNVERIFIED",
        "scientific_suitability": "UNVERIFIED",
    }
    assert result["execution_permitted"] is False


def test_invalid_crs_units_vertical_datum_and_spatial_coverage_are_reported(
    tmp_path: Path,
) -> None:
    configuration = _complete_configuration(tmp_path)
    configuration["inputs"]["terrain"]["crs"] = "EPSG:4326"
    configuration["inputs"]["channel_geometry"]["units"]["vertical"] = "furlong"
    configuration["inputs"]["water_level_observations"]["vertical_datum"] = "OTHER"
    configuration["inputs"]["rainfall_forcing"]["units"]["rainfall"] = "mm/day"
    configuration["inputs"]["rainfall_forcing"]["coverage_bounds_wgs84"] = [
        80.0,
        16.0,
        81.0,
        17.0,
    ]

    result = validate_model_configuration(configuration, tmp_path)

    assert result["technical_status"] == "INVALID"
    assert any("does not match model.horizontal_crs" in error for error in result["errors"])
    assert any("unsupported" in error for error in result["errors"])
    assert any("vertical_datum does not match" in error for error in result["errors"])
    assert any("units.rainfall does not match" in error for error in result["errors"])
    assert any("does not overlap" in error for error in result["errors"])


def test_invalid_time_window_and_unzoned_time_series_timestamps_are_rejected(
    tmp_path: Path,
) -> None:
    configuration = _complete_configuration(tmp_path)
    configuration["time_window"]["start_utc"] = "2025-01-02T00:00:00Z"
    configuration["inputs"]["rainfall_forcing"]["path"] = "inputs/unzoned.csv"
    bad_path = tmp_path / "inputs" / "unzoned.csv"
    _write_csv(bad_path, ["timestamp", "value"], [["2025-01-01 01:00:00", "1"]])
    configuration["inputs"]["rainfall_forcing"]["sha256"] = hashlib.sha256(
        bad_path.read_bytes()
    ).hexdigest()

    result = validate_model_configuration(configuration, tmp_path)

    assert result["technical_status"] == "INVALID"
    assert any("must be before end_utc" in error for error in result["errors"])
    assert any("explicit timezone offset" in error for error in result["errors"])


def test_duplicate_time_series_timestamps_are_rejected(tmp_path: Path) -> None:
    configuration = _complete_configuration(tmp_path)
    path = tmp_path / configuration["inputs"]["rainfall_forcing"]["path"]
    _write_csv(
        path,
        ["timestamp", "value"],
        [
            ["2025-01-01T00:00:00Z", "1.0"],
            ["2025-01-01T00:00:00Z", "2.0"],
        ],
    )
    configuration["inputs"]["rainfall_forcing"]["sha256"] = hashlib.sha256(
        path.read_bytes()
    ).hexdigest()

    result = validate_model_configuration(configuration, tmp_path)

    assert result["technical_status"] == "INVALID"
    assert any("strictly increasing and unique" in error for error in result["errors"])


def test_time_series_order_is_checked_per_declared_station(tmp_path: Path) -> None:
    configuration = _complete_configuration(tmp_path)
    rainfall = configuration["inputs"]["rainfall_forcing"]
    path = tmp_path / rainfall["path"]
    _write_csv(
        path,
        ["timestamp", "value", "station"],
        [
            ["2025-01-01T00:00:00Z", "1.0", "station-a"],
            ["2025-01-01T00:00:00Z", "2.0", "station-b"],
            ["2025-01-01T01:00:00Z", "3.0", "station-a"],
            ["2025-01-01T01:00:00Z", "4.0", "station-b"],
        ],
    )
    rainfall["required_columns"].append("station")
    rainfall["series_key_columns"] = ["station"]
    rainfall["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()

    result = validate_model_configuration(configuration, tmp_path)

    assert result["technical_status"] == "READY"


def test_file_hash_path_boundary_and_malformed_geojson_are_checked(
    tmp_path: Path,
) -> None:
    configuration = _complete_configuration(tmp_path)
    terrain = configuration["inputs"]["terrain"]
    terrain["sha256"] = "0" * 64
    configuration["inputs"]["initial_conditions"]["path"] = "../outside.json"
    channel = configuration["inputs"]["channel_geometry"]
    channel_path = tmp_path / channel["path"]
    channel_path.write_text("{malformed", encoding="utf-8")
    channel["sha256"] = hashlib.sha256(channel_path.read_bytes()).hexdigest()
    channel["format"] = "GeoJSON"

    result = validate_model_configuration(configuration, tmp_path)

    assert result["technical_status"] == "INVALID"
    assert any("sha256 does not match" in error for error in result["errors"])
    assert any("inside the project root" in error for error in result["errors"])
    assert any("file format validation failed" in error for error in result["errors"])


def test_missing_required_input_is_distinguished_from_invalid_input(
    tmp_path: Path,
) -> None:
    configuration = _complete_configuration(tmp_path)
    configuration["inputs"]["official_danger_levels"]["path"] = None

    result = validate_model_configuration(configuration, tmp_path)

    assert result["technical_status"] == "MISSING"
    assert "inputs.official_danger_levels.path" in result["missing_fields"]
    assert result["inputs"]["official_danger_levels"]["technical_status"] == "MISSING"


def test_execution_cannot_be_enabled_by_configuration(tmp_path: Path) -> None:
    configuration = _complete_configuration(tmp_path)
    configuration["execution_enabled"] = True

    result = validate_model_configuration(configuration, tmp_path)

    assert result["technical_status"] == "INVALID"
    assert any("execution_enabled must remain false" in error for error in result["errors"])
    assert result["execution_permitted"] is False


def test_source_url_credentials_are_rejected_without_echoing_them(
    tmp_path: Path,
) -> None:
    configuration = _complete_configuration(tmp_path)
    configuration["inputs"]["water_level_observations"]["source_url"] = (
        "https://private-user:private-password@example.invalid/data"
    )

    result = validate_model_configuration(configuration, tmp_path)

    serialized = json.dumps(result)
    assert result["technical_status"] == "INVALID"
    assert "private-user" not in serialized
    assert "private-password" not in serialized
    assert any("without embedded credentials" in error for error in result["errors"])


def test_validation_results_are_deterministic(tmp_path: Path) -> None:
    configuration = _complete_configuration(tmp_path)

    first = validate_model_configuration(configuration, tmp_path)
    second = validate_model_configuration(configuration, tmp_path)

    assert first == second
    json.dumps(first)


def test_danger_level_effective_period_and_gauge_coordinates_are_checked(
    tmp_path: Path,
) -> None:
    configuration = _complete_configuration(tmp_path)
    danger_path = tmp_path / configuration["inputs"]["official_danger_levels"]["path"]
    _write_csv(
        danger_path,
        ["gauge_id", "value", "effective_from", "effective_to"],
        [[
            "fixture-only",
            "1.0",
            "2025-02-01T00:00:00Z",
            "2025-01-01T00:00:00Z",
        ]],
    )
    configuration["inputs"]["official_danger_levels"]["sha256"] = hashlib.sha256(
        danger_path.read_bytes()
    ).hexdigest()
    gauge_path = tmp_path / configuration["inputs"]["gauge_metadata"]["path"]
    _write_csv(
        gauge_path,
        ["gauge_id", "latitude", "longitude"],
        [["fixture-only", "95", "76.25"]],
    )
    configuration["inputs"]["gauge_metadata"]["sha256"] = hashlib.sha256(
        gauge_path.read_bytes()
    ).hexdigest()

    result = validate_model_configuration(configuration, tmp_path)

    assert result["technical_status"] == "INVALID"
    assert any("interval start must be before" in error for error in result["errors"])
    assert any("invalid latitude/longitude" in error for error in result["errors"])


def test_calibration_and_validation_events_must_not_overlap(tmp_path: Path) -> None:
    configuration = _complete_configuration(tmp_path)
    validation = configuration["inputs"]["validation_observations"]
    path = tmp_path / validation["path"]
    _write_csv(
        path,
        ["timestamp", "value", "event_id"],
        [
            ["2025-01-01T00:00:00Z", "1.0", "calibration_observations-event"],
            ["2025-01-01T01:00:00Z", "2.0", "calibration_observations-event"],
        ],
    )
    validation["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()

    result = validate_model_configuration(configuration, tmp_path)

    assert result["technical_status"] == "INVALID"
    assert any("event IDs overlap" in error for error in result["errors"])
