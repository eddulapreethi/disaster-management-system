from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

import pytest

from ml.preprocessing.audit_hydrological_observations import (
    DEFAULT_FILES,
    LEVEL_COLUMN,
    ROOT,
    TIMESTAMP_COLUMN,
    _sqlite_connection,
    audit_file,
)

HEADERS = (
    "SlNo",
    "Station",
    "State LGD Code",
    "District LGD Code",
    "State",
    "River",
    "Basin",
    "Latitude",
    "Longitude",
    TIMESTAMP_COLUMN,
    LEVEL_COLUMN,
)


def _row(
    serial: str,
    timestamp: str,
    level: str,
    **overrides: str,
) -> dict[str, str]:
    row = {
        "SlNo": serial,
        "Station": "Example Gauge",
        "State LGD Code": "1",
        "District LGD Code": "2",
        "State": "Example State",
        "River": "Example River",
        "Basin": "Example Basin",
        "Latitude": "20.25",
        "Longitude": "80.5",
        TIMESTAMP_COLUMN: timestamp,
        LEVEL_COLUMN: level,
    }
    row.update(overrides)
    return row


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=HEADERS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _audit(path: Path, key: str = "fixture") -> dict:
    with _sqlite_connection(path.parent / f"{key}.sqlite3") as database:
        return audit_file(path, database, key)


def test_default_inputs_resolve_to_the_requested_raw_files() -> None:
    assert DEFAULT_FILES == (
        ROOT / "ml" / "datasets" / "hydrological" / "raw" / "godavari_water_level_2021_2025.csv",
        ROOT / "ml" / "datasets" / "hydrological" / "raw" / "krishna_water_level_2021_2025.csv",
    )


def test_exact_duplicates_and_repeated_station_timestamps_are_distinguished(
    tmp_path: Path,
) -> None:
    source = tmp_path / "observations.csv"
    first = _row("1", "01-01-2025 00:00", "2.5")
    _write_csv(
        source,
        [
            first,
            first.copy(),
            _row("3", "01-01-2025 00:00", "2.6"),
        ],
    )

    result = _audit(source)

    assert result["duplicate_checks"] == {
        "exact_duplicate_rows": 1,
        "duplicate_station_timestamp_records": 2,
        "repeated_station_timestamp_records_with_different_water_level": 1,
        "station_identity": "case-folded Station name + State LGD Code + District LGD Code",
    }


def test_missing_identity_timestamp_bad_numeric_and_malformed_row_are_reported(
    tmp_path: Path,
) -> None:
    source = tmp_path / "observations.csv"
    _write_csv(
        source,
        [
            _row("1", "", "not-a-number", Station="", **{"State LGD Code": ""}),
            _row("2", "not-a-date", "Infinity"),
        ],
    )
    with source.open("a", encoding="utf-8", newline="") as stream:
        stream.write("malformed,row\n")

    result = _audit(source)

    assert result["row_count"] == 3
    assert result["malformed_csv_rows"] == 1
    assert result["records_missing_station_identity"] == 2
    assert result["timestamp_parse_failures"] == 3
    assert result["missing_values"][TIMESTAMP_COLUMN]["count"] == 2
    assert result["numeric_checks"]["parse_failures"][LEVEL_COLUMN] == 1
    assert result["numeric_checks"]["nonfinite_values"][LEVEL_COLUMN] == 1


def test_timestamp_order_and_gap_statistics_are_derived_from_data(
    tmp_path: Path,
) -> None:
    source = tmp_path / "observations.csv"
    _write_csv(
        source,
        [
            _row("1", "01-01-2025 00:00", "1"),
            _row("2", "01-01-2025 01:00", "1"),
            _row("3", "01-01-2025 04:00", "1"),
            _row("4", "01-01-2025 02:00", "1"),
        ],
    )

    result = _audit(source)

    assert result["timestamp_range"] == {
        "minimum": "2025-01-01T00:00",
        "maximum": "2025-01-01T04:00",
    }
    checks = result["timestamp_checks"]
    assert checks["records_not_in_source_chronological_order_within_station"] == 1
    assert not result["basin_metadata_assessment"][
        "filename_label_matches_supplied_basin_metadata"
    ]
    intervals = checks["sampling_intervals"]
    assert intervals["unique_station_timestamps"] == 4
    assert intervals["exactly_60_minutes"] == 2
    assert intervals["longer_than_60_minutes"] == 1
    assert intervals["largest_gaps"][0]["gap_hours"] == 2.0


def test_empty_and_missing_inputs_have_distinct_statuses(tmp_path: Path) -> None:
    empty = tmp_path / "empty.csv"
    empty.write_bytes(b"")

    assert _audit(empty)["status"] == "EMPTY_OR_HEADERLESS"
    assert _audit(tmp_path / "missing.csv")["status"] == "MISSING"


def test_audit_results_are_repeatable(tmp_path: Path) -> None:
    source = tmp_path / "observations.csv"
    _write_csv(source, [_row("1", "01-01-2025 00:00", "1")])

    assert _audit(source, "run_one") == _audit(source, "run_two")


def test_sqlite_connection_rolls_back_only_when_a_transaction_is_active(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "transaction.sqlite3"
    with sqlite3.connect(database_path) as database:
        database.execute("CREATE TABLE sample (value TEXT)")

    with pytest.raises(ValueError, match="primary failure"):
        with _sqlite_connection(database_path) as database:
            database.execute("INSERT INTO sample VALUES ('uncommitted')")
            raise ValueError("primary failure")

    with sqlite3.connect(database_path) as database:
        assert database.execute("SELECT COUNT(*) FROM sample").fetchone()[0] == 0


def test_cleanup_failure_does_not_replace_the_original_exception(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class FailingRollbackConnection:
        in_transaction = True

        def rollback(self) -> None:
            raise sqlite3.OperationalError("cleanup rollback failure")

        def close(self) -> None:
            pass

    connection = FailingRollbackConnection()
    monkeypatch.setattr(
        "ml.preprocessing.audit_hydrological_observations.sqlite3.connect",
        lambda _path: connection,
    )

    with pytest.raises(ValueError, match="original audit failure") as captured:
        with _sqlite_connection(tmp_path / "unused.sqlite3"):
            raise ValueError("original audit failure")

    notes = getattr(captured.value, "__notes__", [])
    assert any("cleanup rollback failure" in note for note in notes)


def test_sqlite_cleanup_does_not_rollback_when_no_transaction_is_active(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class IdleConnection:
        in_transaction = False

        def rollback(self) -> None:
            raise AssertionError("rollback must not run without an active transaction")

        def close(self) -> None:
            pass

    connection = IdleConnection()
    monkeypatch.setattr(
        "ml.preprocessing.audit_hydrological_observations.sqlite3.connect",
        lambda _path: connection,
    )

    with pytest.raises(ValueError, match="original audit failure"):
        with _sqlite_connection(tmp_path / "unused.sqlite3"):
            raise ValueError("original audit failure")
