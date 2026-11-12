import csv
from pathlib import Path

import pytest

from ml.preprocessing.profile_hydrological_forecasting_feasibility import (
    LEVEL_COLUMN,
    TIMESTAMP_COLUMN,
    build_report,
    profile_csv,
    render_markdown,
)


HEADERS = (
    "SlNo",
    "Station",
    "State LGD Code",
    "District LGD Code",
    TIMESTAMP_COLUMN,
    LEVEL_COLUMN,
    "Is_DischargeDataAvailable",
)


def _row(
    serial: str,
    timestamp: str,
    level: str,
    *,
    station: str = "Synthetic Gauge",
    state_code: str = "01",
    district_code: str = "002",
    discharge_available: str = "No",
) -> dict[str, str]:
    return {
        "SlNo": serial,
        "Station": station,
        "State LGD Code": state_code,
        "District LGD Code": district_code,
        TIMESTAMP_COLUMN: timestamp,
        LEVEL_COLUMN: level,
        "Is_DischargeDataAvailable": discharge_available,
    }


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=HEADERS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def test_streaming_profile_distinguishes_duplicates_conflicts_and_irregular_intervals(
    tmp_path: Path,
) -> None:
    source = tmp_path / "synthetic_only.csv"
    first = _row("1", "01-01-2025 00:00", "5.0")
    _write_csv(
        source,
        [
            first,
            first.copy(),
            _row("3", "01-01-2025 00:00", "-7.0"),
            _row("4", "01-01-2025 00:30", "not-a-number"),
            _row("5", "bad-time", "Infinity"),
            _row("6", "", ""),
            _row("7", "01-01-2025 01:00", "10", station=""),
        ],
    )
    with source.open("a", encoding="utf-8", newline="") as stream:
        stream.write("malformed,row\n")
    original_bytes = source.read_bytes()

    result = profile_csv(source, "synthetic_test", temporary_directory=tmp_path)

    assert source.read_bytes() == original_bytes
    assert result["row_count"] == 8
    assert result["schema"]["malformed_rows"] == 1
    assert result["station_coverage"]["audit_identity_count"] == 1
    assert result["station_coverage"]["missing_identity_rows"] == 1
    assert result["time_coverage"]["timezone_representation"] == "timezone-naive only"
    assert result["time_coverage"]["timezone_inferred"] is False
    assert result["time_coverage"]["nonempty_parse_failures"] == 1
    assert result["time_coverage"]["missing_timestamps"] == 1
    assert result["sampling_intervals"]["unique_station_timestamps"] == 2
    assert result["sampling_intervals"]["consecutive_intervals"] == 1
    assert result["sampling_intervals"]["shorter_than_60_minutes"] == 1
    assert result["duplicates"]["exact_duplicate_rows"] == 1
    assert result["duplicates"]["repeated_station_timestamp_rows_beyond_first"] == 2
    assert result["duplicates"]["repeated_station_timestamp_keys"] == 1
    assert (
        result["duplicates"][
            "repeated_station_timestamp_rows_with_level_different_from_first"
        ]
        == 1
    )
    assert result["water_level"]["negative_values_flagged_for_review"] == 1
    assert result["water_level"]["invalid_numeric_values"] == 1
    assert result["water_level"]["nonfinite_values"] == 1
    assert result["water_level"]["minimum"] == -7.0
    assert result["water_level"]["maximum"] == 10.0


def test_profile_reports_missing_and_empty_files_without_creating_data(
    tmp_path: Path,
) -> None:
    with pytest.raises(FileNotFoundError, match="Required hydrological CSV not found"):
        profile_csv(tmp_path / "missing.csv", "missing")

    empty = tmp_path / "empty.csv"
    empty.write_bytes(b"")
    with pytest.raises(ValueError, match="empty or has no header"):
        profile_csv(empty, "empty")


def test_mixed_timezone_awareness_does_not_produce_interval_statistics(
    tmp_path: Path,
) -> None:
    source = tmp_path / "mixed_timezones.csv"
    _write_csv(
        source,
        [
            _row("1", "2025-01-01T00:00:00", "1"),
            _row("2", "2025-01-01T01:00:00+05:30", "2"),
        ],
    )

    result = profile_csv(source, "synthetic_mixed_timezone", temporary_directory=tmp_path)

    assert (
        result["time_coverage"]["timezone_representation"]
        == "mixed timezone-aware and timezone-naive"
    )
    assert (
        result["sampling_intervals"]["status"]
        == "NOT_MEASURED_MIXED_TIMEZONE_AWARENESS"
    )
    assert result["sampling_intervals"]["consecutive_intervals"] is None


def test_report_blocks_one_hour_target_and_joins_without_authoritative_inputs(
    tmp_path: Path,
) -> None:
    source = tmp_path / "synthetic_only.csv"
    _write_csv(source, [_row("1", "01-01-2025 00:00", "4")])
    manifest = tmp_path / "not_available.json"

    report = build_report((source,), processed_manifest=manifest)
    markdown = render_markdown(report)

    assert report["overall_status"] == "NOT_READY"
    assert report["candidate_forecasting_target"]["status"] == "NOT_JUSTIFIED"
    assert report["auxiliary_data_join_review"]["rainfall_or_discharge_join_approved"] is False
    assert report["readiness_gate_snapshot"]["status"] == "BLOCKED"
    assert "NOT_READY" in markdown
    assert "not a validated flood prediction" in markdown
    assert "Potential data leakage risks" in markdown
