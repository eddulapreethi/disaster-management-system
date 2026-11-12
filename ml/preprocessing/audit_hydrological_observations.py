from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone
import heapq
import json
import math
from pathlib import Path
import sqlite3
import tempfile
from typing import Any, Iterator


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FILES = (
    ROOT / "ml" / "datasets" / "hydrological" / "raw" / "godavari_water_level_2021_2025.csv",
    ROOT / "ml" / "datasets" / "hydrological" / "raw" / "krishna_water_level_2021_2025.csv",
)
TIMESTAMP_COLUMN = "Data Acquisition Time"
LEVEL_COLUMN = "River Water Level Telemetry Hourly (meter)"
MISSING_MARKERS = {"", "-", "na", "n/a", "null", "none", "nan"}
NUMERIC_COLUMNS = (
    "Latitude",
    "Longitude",
    "RL_of_zeroGauge",
    "MeanSeaLevel",
    LEVEL_COLUMN,
)
METADATA_COLUMNS = (
    "State",
    "District",
    "River",
    "Basin",
    "Agency",
    "Latitude",
    "Longitude",
    "RL_of_zeroGauge",
    "MeanSeaLevel",
)


def _is_missing(value: str) -> bool:
    return value.strip().casefold() in MISSING_MARKERS


def _parse_timestamp(value: str) -> datetime:
    text = value.strip()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return datetime.strptime(text, "%d-%m-%Y %H:%M")


def _station_identity(row: dict[str, str]) -> tuple[str, str, str] | None:
    name = row.get("Station", "").strip()
    state_code = row.get("State LGD Code", "").strip()
    district_code = row.get("District LGD Code", "").strip()
    if not name or not state_code or not district_code:
        return None
    return name.casefold(), state_code, district_code


def _as_number(value: str) -> float | None:
    if _is_missing(value):
        return None
    try:
        result = float(value.strip())
    except ValueError:
        return None
    return result if math.isfinite(result) else None


def _record_cleanup_error(original: BaseException, cleanup: BaseException) -> None:
    note = f"SQLite cleanup also failed: {type(cleanup).__name__}: {cleanup}"
    add_note = getattr(original, "add_note", None)
    if add_note is not None:
        add_note(note)
    else:
        setattr(original, "sqlite_cleanup_error", note)


@contextmanager
def _sqlite_connection(path: Path) -> Iterator[sqlite3.Connection]:
    database = sqlite3.connect(path)
    try:
        yield database
    except BaseException as original:
        if database.in_transaction:
            try:
                database.rollback()
            except BaseException as cleanup:
                _record_cleanup_error(original, cleanup)
        try:
            database.close()
        except BaseException as cleanup:
            _record_cleanup_error(original, cleanup)
        raise
    else:
        try:
            if database.in_transaction:
                database.commit()
        except BaseException as original:
            if database.in_transaction:
                try:
                    database.rollback()
                except BaseException as cleanup:
                    _record_cleanup_error(original, cleanup)
            try:
                database.close()
            except BaseException as cleanup:
                _record_cleanup_error(original, cleanup)
            raise
        database.close()


def audit_file(path: Path, database: sqlite3.Connection, dataset_key: str) -> dict[str, Any]:
    if not path.is_file():
        return {"path": str(path), "status": "MISSING"}

    counts: Counter[str] = Counter()
    missing: Counter[str] = Counter()
    markers: dict[str, Counter[str]] = defaultdict(Counter)
    parse_failures: Counter[str] = Counter()
    numeric_min: dict[str, float] = {}
    numeric_max: dict[str, float] = {}
    nonfinite: Counter[str] = Counter()
    year_counts: Counter[int] = Counter()
    station_rows: dict[tuple[str, str, str], dict[str, Any]] = {}
    station_year_counts: Counter[tuple[tuple[str, str, str], int]] = Counter()
    timestamp_failures = 0
    missing_station_identity = 0
    invalid_coordinate_rows = 0
    missing_coordinate_rows = 0
    negative_levels = 0
    zero_levels = 0
    source_order_regressions = 0
    latest_source_time: dict[tuple[str, str, str], datetime] = {}
    row_count = 0
    malformed_rows = 0
    minimum_timestamp: datetime | None = None
    maximum_timestamp: datetime | None = None

    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        sample = stream.read(65536)
        stream.seek(0)
        first_line = sample.splitlines()[0] if sample.splitlines() else ""
        if not first_line.strip():
            return {"path": str(path), "status": "EMPTY_OR_HEADERLESS"}
        try:
            dialect = csv.Sniffer().sniff(first_line, delimiters=",;\t|")
        except csv.Error as error:
            raise ValueError(f"{path}: unable to determine the CSV delimiter.") from error
        reader = csv.reader(stream, dialect)
        header = next(reader, None)
        if not header:
            return {"path": str(path), "status": "EMPTY_OR_HEADERLESS"}
        if len(set(header)) != len(header):
            raise ValueError(f"{path}: duplicate CSV column names prevent an unambiguous audit.")

        column_positions = {name: index for index, name in enumerate(header)}
        database.execute(
            "CREATE TABLE IF NOT EXISTS station_times "
            "(dataset TEXT NOT NULL, station_key TEXT NOT NULL, timestamp TEXT NOT NULL, "
            "station_name TEXT NOT NULL, state TEXT NOT NULL, water_level TEXT NOT NULL, "
            "PRIMARY KEY(dataset, station_key, timestamp))"
        )
        database.execute(
            "CREATE TABLE IF NOT EXISTS exact_rows "
            "(dataset TEXT NOT NULL, payload BLOB NOT NULL, "
            "PRIMARY KEY(dataset, payload)) WITHOUT ROWID"
        )

        for raw_row in reader:
            row_count += 1
            if row_count % 10000 == 1 and row_count > 1:
                database.commit()
            if len(raw_row) != len(header):
                malformed_rows += 1
            values = [
                raw_row[index] if index < len(raw_row) else ""
                for index in range(len(header))
            ]
            row = dict(zip(header, values))
            for name, value in row.items():
                counts[name] += 1
                if _is_missing(value):
                    missing[name] += 1
                    if value.strip():
                        markers[name][value.strip()] += 1

            payload = json.dumps(
                raw_row, ensure_ascii=False, separators=(",", ":")
            ).encode("utf-8")
            exact_insert = database.execute(
                "INSERT OR IGNORE INTO exact_rows (dataset, payload) VALUES (?, ?)",
                (dataset_key, payload),
            )
            if exact_insert.rowcount == 0:
                counts["exact_duplicate_rows"] += 1

            identity = _station_identity(row)
            if identity is None:
                missing_station_identity += 1
            else:
                station = station_rows.setdefault(
                    identity,
                    {
                        "display_name": row.get("Station", "").strip(),
                        "state": row.get("State", "").strip(),
                        "record_count": 0,
                        "years": Counter(),
                        "metadata": {field: set() for field in METADATA_COLUMNS},
                        "source_order_regressions": 0,
                        "interval_count": 0,
                        "exact_hour_intervals": 0,
                        "short_intervals": 0,
                        "long_intervals": 0,
                        "longest_gap_seconds": 0,
                    },
                )
                station["record_count"] += 1
                for field in METADATA_COLUMNS:
                    value = row.get(field, "").strip()
                    if not _is_missing(value):
                        station["metadata"][field].add(value)

            lat = _as_number(row.get("Latitude", ""))
            lon = _as_number(row.get("Longitude", ""))
            if lat is None or lon is None:
                missing_coordinate_rows += 1
            elif not (-90 <= lat <= 90 and -180 <= lon <= 180):
                invalid_coordinate_rows += 1

            for field in NUMERIC_COLUMNS:
                if field not in column_positions:
                    continue
                value = row.get(field, "")
                if _is_missing(value):
                    continue
                parsed = _as_number(value)
                if parsed is None:
                    try:
                        if not math.isfinite(float(value.strip())):
                            nonfinite[field] += 1
                        else:
                            parse_failures[field] += 1
                    except ValueError:
                        parse_failures[field] += 1
                    continue
                numeric_min[field] = min(numeric_min.get(field, parsed), parsed)
                numeric_max[field] = max(numeric_max.get(field, parsed), parsed)
                if field == LEVEL_COLUMN:
                    negative_levels += parsed < 0
                    zero_levels += parsed == 0

            timestamp_text = row.get(TIMESTAMP_COLUMN, "").strip()
            try:
                observed_at = _parse_timestamp(timestamp_text)
            except ValueError:
                timestamp_failures += 1
                continue

            year_counts[observed_at.year] += 1
            minimum_timestamp = (
                observed_at
                if minimum_timestamp is None
                else min(minimum_timestamp, observed_at)
            )
            maximum_timestamp = (
                observed_at
                if maximum_timestamp is None
                else max(maximum_timestamp, observed_at)
            )
            if identity is None:
                continue
            station_year_counts[(identity, observed_at.year)] += 1
            station_rows[identity]["years"][observed_at.year] += 1
            previous = latest_source_time.get(identity)
            if previous is not None and observed_at < previous:
                source_order_regressions += 1
                station_rows[identity]["source_order_regressions"] += 1
            if previous is None or observed_at > previous:
                latest_source_time[identity] = observed_at

            station_key = json.dumps(identity, ensure_ascii=False, separators=(",", ":"))
            inserted = database.execute(
                "INSERT OR IGNORE INTO station_times "
                "(dataset, station_key, timestamp, station_name, state, water_level) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    dataset_key,
                    station_key,
                    observed_at.isoformat(timespec="minutes"),
                    row.get("Station", "").strip(),
                    row.get("State", "").strip(),
                    row.get(LEVEL_COLUMN, ""),
                ),
            )
            if inserted.rowcount == 0:
                counts["duplicate_station_timestamp"] += 1
                first_level = database.execute(
                    "SELECT water_level FROM station_times "
                    "WHERE dataset = ? AND station_key = ? AND timestamp = ?",
                    (
                        dataset_key,
                        station_key,
                        observed_at.isoformat(timespec="minutes"),
                    ),
                ).fetchone()[0]
                if first_level != row.get(LEVEL_COLUMN, ""):
                    counts["duplicate_station_timestamp_different_level"] += 1

    database.commit()

    interval_counts: Counter[int] = Counter()
    gap_count = 0
    short_interval_count = 0
    largest_gaps: list[tuple[int, int, dict[str, Any]]] = []
    timestamp_total = 0
    gap_sequence = 0
    # Iterate in station/time order so only one previous timestamp per station is needed.
    cursor = database.execute(
        "SELECT station_key, timestamp, station_name, state FROM station_times "
        "WHERE dataset = ? ORDER BY station_key, timestamp",
        (dataset_key,),
    )
    previous_by_station: dict[str, tuple[datetime, str, str]] = {}
    for station_key, timestamp_text, station_name, state in cursor:
        timestamp_total += 1
        current = datetime.fromisoformat(timestamp_text)
        previous = previous_by_station.get(station_key)
        if previous is not None:
            delta = int((current - previous[0]).total_seconds())
            interval_counts[delta] += 1
            identity = tuple(json.loads(station_key))
            station = station_rows[identity]
            station["interval_count"] += 1
            if delta > 3600:
                gap_count += 1
                station["long_intervals"] += 1
                station["longest_gap_seconds"] = max(
                    station["longest_gap_seconds"], delta
                )
                gap_sequence += 1
                gap = {
                    "station": station_name,
                    "state": state,
                    "from": previous[0].isoformat(timespec="minutes"),
                    "to": current.isoformat(timespec="minutes"),
                    "gap_hours": round(delta / 3600, 3),
                }
                heapq.heappush(largest_gaps, (delta, gap_sequence, gap))
                if len(largest_gaps) > 20:
                    heapq.heappop(largest_gaps)
            elif delta < 3600:
                short_interval_count += 1
                station["short_intervals"] += 1
            else:
                station["exact_hour_intervals"] += 1
        previous_by_station[station_key] = (current, station_name, state)

    largest_gaps_output = [
        gap for _, _, gap in sorted(largest_gaps, reverse=True)
    ]

    stations: list[dict[str, Any]] = []
    for identity, station in station_rows.items():
        metadata = station.pop("metadata")
        entry: dict[str, Any] = {
            "station": station["display_name"],
            "State": station["state"],
            "state_lgd_code": identity[1],
            "district_lgd_code": identity[2],
            "record_count": station["record_count"],
            "consecutive_intervals": station["interval_count"],
            "exactly_60_minute_intervals": station["exact_hour_intervals"],
            "shorter_intervals": station["short_intervals"],
            "longer_intervals": station["long_intervals"],
            "longest_interval_over_60_minutes": (
                round(station["longest_gap_seconds"] / 3600, 3)
                if station["longest_gap_seconds"]
                else None
            ),
            "records_by_year": {
                str(year): count
                for year, count in sorted(station["years"].items())
            },
            "source_order_regressions": station["source_order_regressions"],
        }
        for field in METADATA_COLUMNS:
            values = sorted(metadata[field])
            entry[field] = values
            if len(values) > 1:
                entry.setdefault("inconsistent_metadata_fields", []).append(field)
        stations.append(entry)
    stations.sort(key=lambda station: (station["State"], station["station"].casefold()))
    inconsistent_metadata_fields: Counter[str] = Counter()
    for station in stations:
        inconsistent_metadata_fields.update(station.get("inconsistent_metadata_fields", []))

    missing_summary = {
        name: {
            "count": missing[name],
            "percent": round(100 * missing[name] / row_count, 4) if row_count else 0,
            "nonblank_missing_markers": dict(sorted(markers[name].items())),
        }
        for name in header
    }
    interval_summary = {
        "unique_station_timestamps": timestamp_total,
        "consecutive_intervals": sum(interval_counts.values()),
        "exactly_60_minutes": interval_counts[3600],
        "shorter_than_60_minutes": short_interval_count,
        "longer_than_60_minutes": gap_count,
        "common_interval_minutes": [
            {"minutes": seconds / 60, "count": count}
            for seconds, count in interval_counts.most_common(12)
        ],
        "largest_gaps": largest_gaps_output,
    }
    distinct_rivers = sorted(
        {value for station in stations for value in station["River"]}
    )
    distinct_basins = sorted(
        {value for station in stations for value in station["Basin"]}
    )
    expected_basin_label = path.name.split("_", maxsplit=1)[0].casefold()
    basin_values = {value.casefold() for value in distinct_basins}
    basin_match = expected_basin_label in basin_values

    result = {
        "path": str(path),
        "status": "AUDITED",
        "file_size_bytes": path.stat().st_size,
        "encoding": "UTF-8 with optional BOM",
        "delimiter": dialect.delimiter,
        "row_count": row_count,
        "columns": [
            {
                "name": name,
                "raw_csv_type": "string",
                "semantic_type": (
                    "timestamp text (DD-MM-YYYY HH:MM; timezone not supplied)"
                    if name == TIMESTAMP_COLUMN
                    else "decimal numeric text"
                    if name in NUMERIC_COLUMNS
                    else "integer-like identifier text"
                    if name in {"SlNo", "State LGD Code", "District LGD Code"}
                    else "categorical/text"
                ),
            }
            for name in header
        ],
        "timestamp_range": {
            "minimum": minimum_timestamp.isoformat(timespec="minutes")
            if minimum_timestamp
            else None,
            "maximum": maximum_timestamp.isoformat(timespec="minutes")
            if maximum_timestamp
            else None,
        },
        "timestamp_parse_failures": timestamp_failures,
        "records_by_calendar_year": {
            str(year): count for year, count in sorted(year_counts.items())
        },
        "distinct_rivers": distinct_rivers,
        "distinct_basins": distinct_basins,
        "basin_metadata_assessment": {
            "expected_label_from_filename": expected_basin_label,
            "supplied_basin_values": distinct_basins,
            "filename_label_matches_supplied_basin_metadata": basin_match,
            "evidence_boundary": (
                "This compares supplied metadata with the filename label only; it does not "
                "independently verify hydrological basin membership."
            ),
        },
        "distinct_states": sorted(
            {value for station in stations for value in station["State"]}
        ),
        "station_count": len(stations),
        "stations": stations,
        "metadata_consistency": {
            "stations_with_inconsistent_metadata": sum(
                bool(station.get("inconsistent_metadata_fields")) for station in stations
            ),
            "inconsistent_field_station_counts": dict(
                sorted(inconsistent_metadata_fields.items())
            ),
        },
        "missing_values": missing_summary,
        "numeric_checks": {
            "minima": numeric_min,
            "maxima": numeric_max,
            "parse_failures": dict(parse_failures),
            "nonfinite_values": dict(nonfinite),
            "invalid_coordinate_rows": invalid_coordinate_rows,
            "missing_or_unparseable_coordinate_pairs": missing_coordinate_rows,
            "negative_water_levels": negative_levels,
            "zero_water_levels": zero_levels,
        },
        "duplicate_checks": {
            "exact_duplicate_rows": counts["exact_duplicate_rows"],
            "duplicate_station_timestamp_records": counts["duplicate_station_timestamp"],
            "repeated_station_timestamp_records_with_different_water_level": (
                counts["duplicate_station_timestamp_different_level"]
            ),
            "station_identity": (
                "case-folded Station name + State LGD Code + District LGD Code"
            ),
        },
        "timestamp_checks": {
            "timezone": "timezone-naive source timestamps; no timezone inferred",
            "records_not_in_source_chronological_order_within_station": source_order_regressions,
            "sampling_intervals": interval_summary,
        },
        "malformed_csv_rows": malformed_rows,
        "records_missing_station_identity": missing_station_identity,
    }
    database.execute("DELETE FROM station_times WHERE dataset = ?", (dataset_key,))
    database.execute("DELETE FROM exact_rows WHERE dataset = ?", (dataset_key,))
    database.commit()
    return result


def _build_report(results: list[dict[str, Any]], command: str) -> dict[str, Any]:
    for result in results:
        warnings: list[str] = []
        if result["malformed_csv_rows"]:
            warnings.append(f"{result['malformed_csv_rows']} malformed CSV rows")
        if result["timestamp_parse_failures"]:
            warnings.append(f"{result['timestamp_parse_failures']} timestamp parse failures")
        if result["records_missing_station_identity"]:
            warnings.append(f"{result['records_missing_station_identity']} rows missing station identity")
        if result["duplicate_checks"]["exact_duplicate_rows"]:
            warnings.append(
                f"{result['duplicate_checks']['exact_duplicate_rows']} exact duplicate rows"
            )
        if result["duplicate_checks"]["duplicate_station_timestamp_records"]:
            warnings.append(
                f"{result['duplicate_checks']['duplicate_station_timestamp_records']} repeated station/timestamp records"
            )
        if result["numeric_checks"]["negative_water_levels"]:
            warnings.append(
                f"{result['numeric_checks']['negative_water_levels']} negative water-level values require review"
            )
        if result["missing_values"].get(LEVEL_COLUMN, {}).get("count"):
            warnings.append(
                f"{result['missing_values'][LEVEL_COLUMN]['count']} water-level values are missing"
            )
        if not result["basin_metadata_assessment"][
            "filename_label_matches_supplied_basin_metadata"
        ]:
            warnings.append("filename label does not match supplied basin metadata")
        if result["metadata_consistency"]["stations_with_inconsistent_metadata"]:
            warnings.append(
                f"{result['metadata_consistency']['stations_with_inconsistent_metadata']} stations have inconsistent metadata"
            )
        result["audit_execution_status"] = "PASS"
        result["data_quality_status"] = "WARNING" if warnings else "PASS"
        result["warnings"] = warnings

    return {
        "report_version": "1.0",
        "audit_date_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "audit_script": str(Path(__file__).resolve()),
        "commands_used": [command],
        "overall_status": "WARNING",
        "audit_implementation": {
            "csv_processing": "streamed row by row",
            "duplicate_detection": (
                "temporary on-disk SQLite tables store complete serialized source rows "
                "and unique station/timestamp keys"
            ),
            "commit_interval": "at most 10000 input rows per transaction batch",
            "rollback_behavior": (
                "rollback is attempted only when SQLite reports an active transaction; "
                "cleanup failures are attached to the original exception"
            ),
        },
        "status_definitions": {
            "PASS": "The specified check completed and met its stated technical criterion.",
            "WARNING": "Audit completed, but quality, provenance, or scientific questions remain.",
            "FAIL": "A required check failed or the audit could not complete.",
            "NOT_CHECKED": "No evidence was available or the check was outside this audit.",
        },
        "files": results,
        "normalization": {
            "status": "NOT_CHECKED",
            "decision": "No normalized output was produced.",
            "reason": (
                "No verified site mapping or confirmed source timezone was supplied. "
                "Do not infer stable gauge IDs, timezones, quality flags, or vertical datums."
            ),
        },
        "provenance_and_licensing": {
            "source_authenticity": "NOT_CHECKED",
            "reuse_license": "NOT_CHECKED",
            "provider_metadata_snapshot": "NOT_CHECKED",
            "stable_station_identifier": "NOT_CHECKED",
            "measurement_datum": "NOT_CHECKED",
            "data_dictionary_and_quality_flags": "NOT_CHECKED",
        },
        "limitations": [
            "Audit success is not scientific validation or readiness for hydraulic modelling.",
            "No missing measurements are imputed and no suspicious or duplicate record is removed.",
            "Timestamp timezone is not inferred; interval calculations use parsed source timestamps.",
            "Station names and administrative codes do not independently authenticate physical gauge identity.",
            "Catalog access labels do not establish licensing or unrestricted reuse rights.",
        ],
        "recommended_next_steps": [
            "Obtain authoritative station IDs and provider documentation for field semantics and QC.",
            "Confirm source timezone, units, vertical datum, coordinates, basin assignment, and reuse terms.",
            "Review reported gaps, duplicates, outliers, and metadata inconsistencies with the data provider.",
            "Only then prepare a normalized derivative with source-row traceability and explicit quality flags.",
        ],
    }


def _render_markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# Stage 2 Part B: Hydrological Data Audit",
        "",
        f"- **Overall status:** {report['overall_status']}",
        f"- **Audit date (UTC):** {report['audit_date_utc']}",
        f"- **Script:** `{report['audit_script']}`",
        f"- **Command:** `{report['commands_used'][0]}`",
        "",
        "Status definitions: PASS means the stated technical check completed; WARNING means "
        "quality, provenance, or scientific questions remain; FAIL means a required check "
        "failed or the audit did not complete; NOT_CHECKED means no evidence was available "
        "or the check was outside this audit.",
        "",
        "This is data preparation only. A successful script run does not establish a validated "
        "flood prediction model or readiness for hydraulic modelling.",
        "",
        "Rows are streamed. Duplicate keys are stored in a temporary on-disk SQLite database, "
        "not in an unbounded Python set; the database is deleted at process exit.",
    ]
    for result in report["files"]:
        duplicate = result["duplicate_checks"]
        missing_fields = result["missing_values"]
        sampling = result["timestamp_checks"]["sampling_intervals"]
        important_missing = {
            name: details["count"]
            for name, details in missing_fields.items()
            if details["count"] and name in {
                "Station",
                "State LGD Code",
                "District LGD Code",
                TIMESTAMP_COLUMN,
                LEVEL_COLUMN,
            }
        }
        lines.extend(
            [
                "",
                f"## {Path(result['path']).name}",
                "",
                f"- **File:** `{result['path']}`",
                f"- **Audit execution / data quality:** "
                f"{result['audit_execution_status']} / {result['data_quality_status']}",
                f"- **Size:** {result['file_size_bytes']} bytes",
                f"- **Encoding / delimiter:** {result['encoding']} / `{result['delimiter']}`",
                f"- **Rows / stations:** {result['row_count']} / {result['station_count']}",
                f"- **Observed timestamp range:** {result['timestamp_range']['minimum']} to "
                f"{result['timestamp_range']['maximum']}",
                "- **Timestamp convention:** source timestamps are timezone-naive; no timezone inferred",
                f"- **Timestamp parse failures:** {result['timestamp_parse_failures']}",
                f"- **Malformed CSV rows:** {result['malformed_csv_rows']}",
                f"- **Rows missing station identity:** {result['records_missing_station_identity']}",
                f"- **Important missing values:** `{json.dumps(important_missing, sort_keys=True)}`",
                f"- **Exact duplicate rows:** {duplicate['exact_duplicate_rows']}",
                "- **Repeated station/timestamp records:** "
                f"{duplicate['duplicate_station_timestamp_records']}",
                "- **Repeated station/timestamp records with a different water level:** "
                f"{duplicate['repeated_station_timestamp_records_with_different_water_level']}",
                f"- **Source-order timestamp regressions:** "
                f"{result['timestamp_checks']['records_not_in_source_chronological_order_within_station']}",
                f"- **Intervals:** {sampling['exactly_60_minutes']} exactly 60 minutes; "
                f"{sampling['shorter_than_60_minutes']} shorter; "
                f"{sampling['longer_than_60_minutes']} longer",
                f"- **Water-level range (source column labeled metres):** "
                f"{result['numeric_checks']['minima'].get(LEVEL_COLUMN)} to "
                f"{result['numeric_checks']['maxima'].get(LEVEL_COLUMN)}; "
                f"{result['numeric_checks']['negative_water_levels']} negative values require review",
                f"- **Distinct river/basin metadata:** `{json.dumps(result['distinct_rivers'], ensure_ascii=False)}` / "
                f"`{json.dumps(result['distinct_basins'], ensure_ascii=False)}`",
                f"- **Filename-to-basin metadata comparison:** "
                f"{result['basin_metadata_assessment']['filename_label_matches_supplied_basin_metadata']} "
                "(not independently verified)",
                f"- **Stations with inconsistent metadata:** "
                f"{result['metadata_consistency']['stations_with_inconsistent_metadata']}",
                f"- **Station states supplied in metadata:** "
                f"`{json.dumps(result['distinct_states'], ensure_ascii=False)}`",
                f"- **Invalid numeric values:** `{json.dumps(result['numeric_checks']['parse_failures'], sort_keys=True)}`",
                f"- **Non-finite numeric values:** `{json.dumps(result['numeric_checks']['nonfinite_values'], sort_keys=True)}`",
            ]
        )
        if result["warnings"]:
            lines.extend(["", "### Warnings", ""])
            lines.extend(f"- {warning}" for warning in result["warnings"])
        lines.extend(["", "### Largest timestamp gaps (top 5)", ""])
        lines.extend(
            f"- {gap['station']} ({gap['state']}): {gap['from']} to {gap['to']} "
            f"({gap['gap_hours']} hours)"
            for gap in sampling["largest_gaps"][:5]
        )
    lines.extend(
        [
            "",
            "## Normalization",
            "",
            f"**{report['normalization']['status']}** — {report['normalization']['reason']}",
            "",
            "## Unresolved provenance and scientific limitations",
            "",
        ]
    )
    lines.extend(f"- **{key}:** {value}" for key, value in report["provenance_and_licensing"].items())
    lines.extend(["", "## Recommended next steps", ""])
    lines.extend(f"{index}. {step}" for index, step in enumerate(report["recommended_next_steps"], 1))
    lines.extend(["", "## Commands", ""])
    lines.extend(f"- `{command}`" for command in report["commands_used"])
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read-only, memory-conscious audit of the two hydrological CSVs."
    )
    parser.add_argument(
        "files",
        nargs="*",
        type=Path,
        default=list(DEFAULT_FILES),
        help="CSV paths; defaults to the two requested raw files.",
    )
    parser.add_argument(
        "--json-report",
        type=Path,
        help="Optional path for a machine-readable report; written only if all inputs audit.",
    )
    parser.add_argument(
        "--markdown-report",
        type=Path,
        help="Optional path for a readable report; written only if all inputs audit.",
    )
    args = parser.parse_args()

    results = []
    with tempfile.TemporaryDirectory(prefix="hydrological-audit-") as temporary_directory:
        database_path = Path(temporary_directory) / "audit.sqlite3"
        with _sqlite_connection(database_path) as database:
            database.execute("PRAGMA temp_store=FILE")
            database.execute("PRAGMA cache_size=-8192")
            for index, path in enumerate(args.files):
                results.append(audit_file(path, database, str(index)))

    if any(result["status"] != "AUDITED" for result in results):
        raise RuntimeError("Refusing to write a report because an input was not audited.")

    command = "python -m ml.preprocessing.audit_hydrological_observations"
    if len(args.files) != len(DEFAULT_FILES) or tuple(args.files) != DEFAULT_FILES:
        command += " " + " ".join(str(path) for path in args.files)
    if args.json_report:
        command += f" --json-report {args.json_report}"
    if args.markdown_report:
        command += f" --markdown-report {args.markdown_report}"
    report = _build_report(results, command)

    print(json.dumps(results, ensure_ascii=False, indent=2))
    for report_path, content in (
        (
            args.json_report,
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        ),
        (args.markdown_report, _render_markdown_report(report)),
    ):
        if report_path:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    main()
