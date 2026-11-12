from __future__ import annotations

import argparse
import csv
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
import heapq
import json
import math
from pathlib import Path
import sqlite3
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FILES = (
    ROOT / "ml" / "datasets" / "hydrological" / "raw" / "godavari_water_level_2021_2025.csv",
    ROOT / "ml" / "datasets" / "hydrological" / "raw" / "krishna_water_level_2021_2025.csv",
)
PROCESSED_MANIFEST = (
    ROOT / "ml" / "datasets" / "hydrological" / "processed"
    / "hydrology_observations.manifest.json"
)
TIMESTAMP_COLUMN = "Data Acquisition Time"
LEVEL_COLUMN = "River Water Level Telemetry Hourly (meter)"
STATION_COLUMNS = ("Station", "State LGD Code", "District LGD Code")
REQUIRED_PROFILE_COLUMNS = (
    *STATION_COLUMNS,
    TIMESTAMP_COLUMN,
    LEVEL_COLUMN,
)
MISSING_MARKERS = {"", "-", "na", "n/a", "null", "none", "nan"}


def _is_missing(value: str | None) -> bool:
    return value is None or value.strip().casefold() in MISSING_MARKERS


def _parse_timestamp(value: str) -> datetime:
    text = value.strip()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return datetime.strptime(text, "%d-%m-%Y %H:%M")


def _timestamp_sort_value(value: datetime) -> datetime:
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _station_identity(row: dict[str, str]) -> tuple[str, str, str] | None:
    name = row.get("Station", "").strip()
    state_code = row.get("State LGD Code", "").strip()
    district_code = row.get("District LGD Code", "").strip()
    if not name or not state_code or not district_code:
        return None
    return name.casefold(), state_code, district_code


def _inferred_kind(name: str, stats: dict[str, int]) -> str:
    total = stats["non_missing"]
    if not total:
        return "unknown (all values missing)"
    if name == TIMESTAMP_COLUMN:
        if stats["timestamp_parseable"] == total:
            return "timestamp text (timezone representation reported separately)"
        if stats["timestamp_parseable"]:
            return "mixed timestamp text / unparseable text"
        return "text (no parseable timestamps)"
    if stats["numeric"] == total:
        return "integer-like numeric text" if stats["integer_like"] == total else "numeric text"
    if stats["numeric"]:
        return "mixed numeric / text"
    return "text"


def profile_csv(
    path: str | Path,
    dataset_id: str,
    *,
    temporary_directory: str | Path | None = None,
) -> dict[str, Any]:
    """Stream one CSV and use temporary SQLite tables for bounded-memory duplicate checks."""
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"Required hydrological CSV not found: {source}")

    temporary_root = Path(temporary_directory) if temporary_directory else None
    with tempfile.TemporaryDirectory(
        prefix="hydrology-profile-", dir=temporary_root
    ) as temporary_name:
        database_path = Path(temporary_name) / "profile.sqlite3"
        with closing(sqlite3.connect(database_path)) as database:
            database.execute("PRAGMA journal_mode=OFF")
            database.execute("PRAGMA synchronous=OFF")
            database.execute(
                "CREATE TABLE exact_rows (payload TEXT PRIMARY KEY) WITHOUT ROWID"
            )
            database.execute(
                "CREATE TABLE station_times ("
                "station_key TEXT NOT NULL, timestamp TEXT NOT NULL, "
                "first_level TEXT, record_count INTEGER NOT NULL, "
                "conflicting_repeats INTEGER NOT NULL DEFAULT 0, "
                "PRIMARY KEY(station_key, timestamp)) WITHOUT ROWID"
            )

            missing: Counter[str] = Counter()
            parse_failures: Counter[str] = Counter()
            lexical_stats: dict[str, Counter[str]] = {}
            station_rows: dict[tuple[str, str, str], dict[str, Any]] = {}
            latest_source_time: dict[tuple[str, str, str], datetime] = {}
            exact_duplicate_rows = 0
            missing_station_identity_rows = 0
            missing_timestamp_rows = 0
            timestamp_aware_rows = 0
            timestamp_naive_rows = 0
            invalid_level_values = 0
            nonfinite_level_values = 0
            negative_levels = 0
            water_level_min: float | None = None
            water_level_max: float | None = None
            minimum_record: dict[str, Any] | None = None
            maximum_record: dict[str, Any] | None = None
            extreme_heap: list[tuple[float, int, dict[str, Any]]] = []
            timestamp_min: datetime | None = None
            timestamp_max: datetime | None = None
            timestamp_parseable_rows = 0
            row_count = 0
            malformed_rows = 0
            column_names: list[str] = []
            missing_required_columns: list[str] = []
            consecutive_intervals = 0

            with source.open("r", encoding="utf-8-sig", newline="") as stream:
                reader = csv.reader(stream)
                header = next(reader, None)
                if not header:
                    raise ValueError(f"{source}: CSV is empty or has no header.")
                if len(set(header)) != len(header):
                    raise ValueError(f"{source}: duplicate CSV column names are ambiguous.")
                column_names = header
                missing_required_columns = sorted(
                    set(REQUIRED_PROFILE_COLUMNS) - set(header)
                )
                lexical_stats = {name: Counter() for name in header}

                for source_row_number, raw_row in enumerate(reader, start=2):
                    row_count += 1
                    if row_count % 10000 == 0:
                        database.commit()
                    if len(raw_row) != len(header):
                        malformed_rows += 1
                        continue

                    row = dict(zip(header, raw_row))
                    for column, value in row.items():
                        stats = lexical_stats[column]
                        if _is_missing(value):
                            missing[column] += 1
                            continue
                        stats["non_missing"] += 1
                        if column == TIMESTAMP_COLUMN:
                            try:
                                _parse_timestamp(value)
                            except ValueError:
                                stats["timestamp_parse_failures"] += 1
                            else:
                                stats["timestamp_parseable"] += 1
                        else:
                            try:
                                numeric = float(value.strip())
                            except ValueError:
                                continue
                            stats["numeric"] += 1
                            if math.isfinite(numeric) and numeric.is_integer():
                                stats["integer_like"] += 1

                    payload = json.dumps(raw_row, ensure_ascii=False, separators=(",", ":"))
                    inserted = database.execute(
                        "INSERT OR IGNORE INTO exact_rows(payload) VALUES (?)", (payload,)
                    )
                    if inserted.rowcount == 0:
                        exact_duplicate_rows += 1

                    identity = _station_identity(row)
                    if identity is None:
                        missing_station_identity_rows += 1
                    else:
                        station = station_rows.setdefault(
                            identity,
                            {
                                "station_name_as_supplied": row["Station"].strip(),
                                "state_code_as_supplied": row["State LGD Code"].strip(),
                                "district_code_as_supplied": row[
                                    "District LGD Code"
                                ].strip(),
                                "record_count": 0,
                                "first_observed_timestamp": None,
                                "last_observed_timestamp": None,
                                "source_order_regressions": 0,
                            },
                        )
                        station["record_count"] += 1

                    raw_timestamp = row.get(TIMESTAMP_COLUMN, "")
                    if _is_missing(raw_timestamp):
                        missing_timestamp_rows += 1
                    else:
                        try:
                            observed_at = _parse_timestamp(raw_timestamp)
                        except ValueError:
                            parse_failures[TIMESTAMP_COLUMN] += 1
                        else:
                            timestamp_parseable_rows += 1
                            if observed_at.tzinfo is None:
                                timestamp_naive_rows += 1
                            else:
                                timestamp_aware_rows += 1
                            ordered_time = _timestamp_sort_value(observed_at)
                            timestamp_min = (
                                ordered_time
                                if timestamp_min is None
                                else min(timestamp_min, ordered_time)
                            )
                            timestamp_max = (
                                ordered_time
                                if timestamp_max is None
                                else max(timestamp_max, ordered_time)
                            )
                            if identity is not None:
                                latest = latest_source_time.get(identity)
                                if latest is not None and ordered_time < latest:
                                    station_rows[identity]["source_order_regressions"] += 1
                                if latest is None or ordered_time > latest:
                                    latest_source_time[identity] = ordered_time

                                first = station_rows[identity]["first_observed_timestamp"]
                                last = station_rows[identity]["last_observed_timestamp"]
                                ordered_text = ordered_time.isoformat(timespec="seconds")
                                if first is None or ordered_text < first:
                                    station_rows[identity]["first_observed_timestamp"] = ordered_text
                                if last is None or ordered_text > last:
                                    station_rows[identity]["last_observed_timestamp"] = ordered_text

                                station_key = json.dumps(
                                    identity, ensure_ascii=False, separators=(",", ":")
                                )
                                level_text = row.get(LEVEL_COLUMN, "")
                                database.execute(
                                    "INSERT INTO station_times "
                                    "(station_key, timestamp, first_level, record_count) "
                                    "VALUES (?, ?, ?, 1) "
                                    "ON CONFLICT(station_key, timestamp) DO UPDATE SET "
                                    "record_count = record_count + 1, "
                                    "conflicting_repeats = conflicting_repeats + "
                                    "CASE WHEN station_times.first_level IS excluded.first_level "
                                    "THEN 0 ELSE 1 END",
                                    (station_key, ordered_text, level_text),
                                )

                    level_text = row.get(LEVEL_COLUMN, "")
                    if _is_missing(level_text):
                        continue
                    try:
                        level = float(level_text.strip())
                    except ValueError:
                        invalid_level_values += 1
                        continue
                    if not math.isfinite(level):
                        nonfinite_level_values += 1
                        continue
                    if level < 0:
                        negative_levels += 1
                    record = {
                        "source_row_number": source_row_number,
                        "station": row.get("Station", ""),
                        "timestamp_as_supplied": raw_timestamp,
                        "water_level_as_supplied": level_text,
                    }
                    if water_level_min is None or level < water_level_min:
                        water_level_min = level
                        minimum_record = record
                    if water_level_max is None or level > water_level_max:
                        water_level_max = level
                        maximum_record = record
                    item = (abs(level), source_row_number, record)
                    if len(extreme_heap) < 10:
                        heapq.heappush(extreme_heap, item)
                    elif item[:2] > extreme_heap[0][:2]:
                        heapq.heapreplace(extreme_heap, item)

            database.commit()
            (
                repeated_station_timestamp_rows,
                conflicting_station_timestamp_rows,
                duplicate_groups,
                conflicting_groups,
                unique_station_timestamps,
            ) = database.execute(
                "SELECT "
                "COALESCE(SUM(record_count - 1), 0), "
                "COALESCE(SUM(conflicting_repeats), 0), "
                "SUM(CASE WHEN record_count > 1 THEN 1 ELSE 0 END), "
                "SUM(CASE WHEN conflicting_repeats > 0 THEN 1 ELSE 0 END), "
                "COUNT(*) FROM station_times"
            ).fetchone()

            interval_counts: Counter[int] = Counter()
            shorter = exactly_hourly = longer = long_gaps = 0
            largest_gaps: list[tuple[float, int, dict[str, Any]]] = []
            previous_by_station: dict[str, tuple[datetime, str]] = {}
            gap_sequence = 0
            mixed_awareness = timestamp_aware_rows > 0 and timestamp_naive_rows > 0
            if not mixed_awareness:
                with closing(
                    database.execute(
                        "SELECT station_key, timestamp FROM station_times "
                        "ORDER BY station_key, timestamp"
                    )
                ) as cursor:
                    for station_key, timestamp_text in cursor:
                        current = datetime.fromisoformat(timestamp_text)
                        previous = previous_by_station.get(station_key)
                        if previous is not None:
                            consecutive_intervals += 1
                            prior_time, _prior_text = previous
                            delta_seconds = (current - prior_time).total_seconds()
                            delta_minutes = delta_seconds / 60
                            if delta_seconds < 3600:
                                shorter += 1
                            elif delta_seconds == 3600:
                                exactly_hourly += 1
                            else:
                                longer += 1
                            if delta_seconds >= 86400:
                                long_gaps += 1
                            if delta_minutes.is_integer():
                                interval_counts[int(delta_minutes)] += 1
                            station_parts = json.loads(station_key)
                            station_name = station_rows.get(
                                tuple(station_parts), {}
                            ).get("station_name_as_supplied", "")
                            gap = {
                                "station_as_supplied": station_name,
                                "from": prior_time.isoformat(timespec="seconds"),
                                "to": current.isoformat(timespec="seconds"),
                                "gap_hours": delta_seconds / 3600,
                            }
                            gap_sequence += 1
                            gap_item = (delta_seconds, gap_sequence, gap)
                            if len(largest_gaps) < 10:
                                heapq.heappush(largest_gaps, gap_item)
                            elif gap_item[:2] > largest_gaps[0][:2]:
                                heapq.heapreplace(largest_gaps, gap_item)
                        previous_by_station[station_key] = (current, timestamp_text)

            inferred_schema = []
            for name in column_names:
                stats = lexical_stats[name]
                inferred_schema.append(
                    {
                        "name": name,
                        "csv_storage_type": "text",
                        "inferred_lexical_kind": _inferred_kind(name, stats),
                        "non_missing_values": stats["non_missing"],
                        "missing_values": missing[name],
                        "numeric_looking_values": stats["numeric"],
                        "parse_failures": (
                            stats["timestamp_parse_failures"]
                            if name == TIMESTAMP_COLUMN
                            else 0
                        ),
                    }
                )

    timestamp_awareness = (
        "timezone-naive only"
        if timestamp_naive_rows and not timestamp_aware_rows
        else "explicit offsets present only"
        if timestamp_aware_rows and not timestamp_naive_rows
        else "mixed timezone-aware and timezone-naive"
        if timestamp_aware_rows and timestamp_naive_rows
        else "no parseable timestamps"
    )
    interval_status = (
        "NOT_MEASURED_MIXED_TIMEZONE_AWARENESS"
        if timestamp_aware_rows and timestamp_naive_rows
        else "MEASURED_FROM_PARSED_SOURCE_TIMESTAMPS"
    )
    top_intervals = [
        {"minutes": minutes, "count": count}
        for minutes, count in interval_counts.most_common(12)
    ]

    return {
        "dataset_id": dataset_id,
        "path": str(source.resolve()),
        "file_size_bytes": source.stat().st_size,
        "status": "PROFILED",
        "schema": {
            "columns": inferred_schema,
            "malformed_rows": malformed_rows,
            "missing_required_columns": missing_required_columns,
        },
        "row_count": row_count,
        "station_coverage": {
            "audit_identity_count": len(station_rows),
            "identity_definition": (
                "case-folded supplied station name + supplied State LGD Code + "
                "supplied District LGD Code; audit grouping only, not verified gauge IDs"
            ),
            "missing_identity_rows": missing_station_identity_rows,
            "stations": sorted(
                station_rows.values(),
                key=lambda item: (
                    item["station_name_as_supplied"].casefold(),
                    item["state_code_as_supplied"],
                    item["district_code_as_supplied"],
                ),
            ),
        },
        "time_coverage": {
            "minimum_parsed_source_time": (
                timestamp_min.isoformat(timespec="seconds") if timestamp_min else None
            ),
            "maximum_parsed_source_time": (
                timestamp_max.isoformat(timespec="seconds") if timestamp_max else None
            ),
            "timezone_representation": timestamp_awareness,
            "timezone_inferred": False,
            "timestamp_semantics": "UNRESOLVED; Data Acquisition Time meaning not established",
            "missing_timestamps": missing_timestamp_rows,
            "nonempty_parse_failures": parse_failures[TIMESTAMP_COLUMN],
            "parseable_timestamps": timestamp_parseable_rows,
            "source_order_regressions_within_audit_identity": sum(
                station["source_order_regressions"] for station in station_rows.values()
            ),
        },
        "sampling_intervals": {
            "status": interval_status,
            "unique_station_timestamps": unique_station_timestamps,
            "consecutive_intervals": None if mixed_awareness else consecutive_intervals,
            "exactly_60_minutes": None if mixed_awareness else exactly_hourly,
            "shorter_than_60_minutes": None if mixed_awareness else shorter,
            "longer_than_60_minutes": None if mixed_awareness else longer,
            "gaps_at_least_24_hours": None if mixed_awareness else long_gaps,
            "common_whole_minute_intervals": top_intervals,
            "largest_gaps": [
                item[2] for item in sorted(largest_gaps, key=lambda item: item[0], reverse=True)
            ],
            "missing_station_identity_rows_excluded_from_intervals": missing_station_identity_rows,
            "interval_basis": (
                "Elapsed time between unique parsed source timestamps. No timezone was added "
                "to naive timestamps; source event semantics remain unknown."
            ),
        },
        "missing_values": dict(sorted(missing.items())),
        "water_level": {
            "source_column": LEVEL_COLUMN,
            "declared_unit_in_header": "meter",
            "unit_verified_for_exact_historical_resource": False,
            "valid_numeric_count": (
                lexical_stats.get(LEVEL_COLUMN, Counter())["non_missing"]
                - invalid_level_values
                - nonfinite_level_values
                if LEVEL_COLUMN in lexical_stats
                else 0
            ),
            "missing_count": missing[LEVEL_COLUMN],
            "invalid_numeric_values": invalid_level_values,
            "nonfinite_values": nonfinite_level_values,
            "negative_values_flagged_for_review": negative_levels,
            "minimum": water_level_min,
            "minimum_record": minimum_record,
            "maximum": water_level_max,
            "maximum_record": maximum_record,
            "largest_absolute_value_examples": [
                item[2] for item in sorted(extreme_heap, key=lambda item: item[0], reverse=True)
            ],
            "interpretation": (
                "Continuous target semantics, unit, sign, vertical datum, QC, and negative/extreme "
                "value meaning remain unresolved. Values were not removed or corrected."
            ),
        },
        "duplicates": {
            "exact_duplicate_rows": exact_duplicate_rows,
            "repeated_station_timestamp_rows_beyond_first": repeated_station_timestamp_rows,
            "repeated_station_timestamp_keys": duplicate_groups or 0,
            "repeated_station_timestamp_rows_with_level_different_from_first": (
                conflicting_station_timestamp_rows
            ),
            "conflicting_station_timestamp_keys": conflicting_groups or 0,
            "duplicates_resolved_or_removed": False,
        },
        "potential_leakage_risks": [
            "Do not random-split this time series: nearby observations and overlapping target windows can leak temporal information across partitions.",
            "Build future targets and lag/rolling predictors within an accepted stable gauge identity, after sorting by verified observation time; never use future or post-issue data in predictors.",
            "Do not use source row numbers, SlNo, export order, fetched_at, or fields generated after the prediction issue time as predictors without a documented availability-time review.",
            "Repeated station/timestamp records and revisions can leak or duplicate samples until provider resolution rules are reviewed.",
            "Unknown station identity, time semantics, timezone, publication delay, and data revision timing prevent establishing what information would actually have been available at forecast issue time.",
            "If the same gauges appear in train and test, results measure temporal generalization on known stations, not transfer to unseen stations; report a separate station-held-out evaluation after authoritative crosswalk review.",
        ],
    }


def _processed_join_context(manifest_path: Path) -> dict[str, Any]:
    if not manifest_path.is_file():
        return {
            "manifest_path": str(manifest_path),
            "status": "NOT_AVAILABLE",
            "rainfall_or_discharge_join_approved": False,
        }
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {
        "manifest_path": str(manifest_path.resolve()),
        "status": "PRESENT_BUT_NOT_A_JOIN_AUTHORIZATION",
        "row_count": manifest.get("row_count"),
        "observation_date_range": manifest.get("observation_date_range"),
        "missing_values": manifest.get("missing_values", {}),
        "training_suitable": manifest.get("training_suitable"),
        "available_columns": [item.get("name") for item in manifest.get("columns", [])],
        "rainfall_or_discharge_join_approved": False,
        "reason": (
            "The existing processed snapshot is a separate collection product. Its manifest "
            "does not establish an authoritative station crosswalk or validated temporal "
            "alignment to these historical raw files; its discharge field is entirely missing "
            "and rainfall is mostly missing. No join or feature was created."
        ),
    }


def build_report(
    files: tuple[Path, ...] = DEFAULT_FILES,
    *,
    processed_manifest: Path = PROCESSED_MANIFEST,
) -> dict[str, Any]:
    datasets = [
        profile_csv(path, path.stem.removesuffix("_water_level_2021_2025"))
        for path in files
    ]
    return {
        "report_version": "1.0",
        "profiled_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "script": str(Path(__file__).resolve()),
        "commands_used": [
            "python -m ml.preprocessing.profile_hydrological_forecasting_feasibility"
        ],
        "overall_status": "NOT_READY",
        "interpretation_boundary": (
            "Read-only dataset profiling and prediction-feasibility review. This is not a "
            "trained or validated water-level forecast and is not a validated flood prediction."
        ),
        "profiling_implementation": {
            "csv_rows": "streamed row by row",
            "duplicate_detection": "temporary SQLite tables on disk; no unbounded per-row Python sets",
            "raw_inputs_modified": False,
            "existing_processed_outputs_modified": False,
        },
        "datasets": datasets,
        "auxiliary_data_join_review": _processed_join_context(processed_manifest),
        "candidate_forecasting_target": {
            "status": "NOT_JUSTIFIED",
            "candidate_definition": (
                "For a provider-identified gauge, predict the valid measured water level at "
                "issue time + 60 minutes using only information available at issue time."
            ),
            "why_not_currently_justified": [
                "Data Acquisition Time semantics and timezone remain unresolved; naive timestamps cannot safely define an issue instant or future horizon.",
                "Observed intervals include both shorter and longer than 60 minutes, so the next row is not reliably a one-hour-ahead target; interpolation/resampling would invent measurements.",
                "Stable physical gauge IDs, duplicate/revision rules, units, sign, datum, QC, and negative/extreme-value semantics remain unresolved.",
                "Observation coverage includes missing levels and large station-specific gaps; no provider coverage or operating-period evidence supports complete windows.",
            ],
            "conditions_before_considering": [
                "Accept authoritative timestamp event semantics, timezone/clock rules, and stable station crosswalk.",
                "Accept exact-resource water-level quantity, unit, sign and datum semantics, quality/sentinel rules, and duplicate/revision handling.",
                "Define and domain-review a target-time matching tolerance and missing-target policy. Do not interpolate absent target values.",
                "Demonstrate sufficient valid observations and coverage per station for the chosen horizon using only evidence-supported records.",
            ],
        },
        "evaluation_plan_if_later_approved": {
            "split": (
                "After all prerequisites are accepted, use globally chronological train/validation/test "
                "periods (initial proposal 70%/15%/15% by time, with boundaries fixed before evaluation). "
                "Assign rows by prediction issue time and purge any target window crossing a split boundary."
            ),
            "embargo": (
                "Apply a temporal purge/embargo at least as long as the forecast horizon plus the "
                "maximum predictor lookback; establish exact duration after the feature contract is defined."
            ),
            "station_grouping": (
                "Primary temporal evaluation may include the same verified gauges across periods and "
                "must be described as known-station generalization. Add a separate station-held-out "
                "group evaluation for unseen-station generalization only after station IDs are verified."
            ),
            "baselines_and_metrics": [
                "Persistence: latest valid same-gauge observation available strictly before issue time, with the same target-time eligibility rules as the model.",
                "Seasonal naive only if authoritative cadence and matching historical horizon are established.",
                "Compare against persistence using MAE and RMSE; report per-station as well as pooled metrics and sample counts. Report metric units only after measurement units are verified.",
                "Do not use random splits or report a single metric without temporal coverage, missing-target, station composition, and baseline context.",
            ],
        },
        "readiness_gate_snapshot": {
            "path": str(
                ROOT / "docs" / "HYDROLOGICAL_METADATA_READINESS_GATE.json"
            ),
            "status": "BLOCKED",
            "fields_unresolved": 30,
            "note": "The profiler does not modify or override the hydrological metadata readiness gate.",
        },
        "blockers": [
            "The metadata readiness gate is BLOCKED and all required fields remain UNRESOLVED.",
            "The exact historical resource provenance, completeness, and reuse terms are not verified.",
            "Timestamp meaning/timezone and stable physical station identities are not verified.",
            "Water-level measurement semantics, units, vertical datum, quality-control rules, and duplicate handling are unresolved.",
            "No verified rainfall/discharge join to these historical station/time records is available.",
        ],
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Stage 2 ML Part 1: Hydrological Forecasting Feasibility",
        "",
        f"- **Status:** {report['overall_status']}",
        f"- **Profiled at (UTC):** {report['profiled_at_utc']}",
        f"- **Script:** `{report['script']}`",
        "",
        report["interpretation_boundary"],
        "",
        "## Dataset profiles",
    ]
    for dataset in report["datasets"]:
        coverage = dataset["time_coverage"]
        level = dataset["water_level"]
        duplicate = dataset["duplicates"]
        intervals = dataset["sampling_intervals"]
        lines.extend(
            [
                "",
                f"### {dataset['dataset_id']}",
                "",
                f"- **File:** `{dataset['path']}`",
                f"- **Rows / audit station identities:** {dataset['row_count']} / "
                f"{dataset['station_coverage']['audit_identity_count']}",
                f"- **Observed timestamps:** {coverage['minimum_parsed_source_time']} to "
                f"{coverage['maximum_parsed_source_time']}",
                f"- **Timezone representation:** {coverage['timezone_representation']}; "
                "no timezone inferred",
                f"- **Sampling intervals:** {intervals['exactly_60_minutes']} exactly 60 minutes; "
                f"{intervals['shorter_than_60_minutes']} shorter; {intervals['longer_than_60_minutes']} longer",
                f"- **Missing water levels:** {level['missing_count']}",
                f"- **Water-level range:** {level['minimum']} to {level['maximum']} "
                f"(header declares metres; not verified)",
                f"- **Negative values flagged:** {level['negative_values_flagged_for_review']}",
                f"- **Exact duplicates:** {duplicate['exact_duplicate_rows']}",
                f"- **Repeated station/timestamp rows beyond first:** "
                f"{duplicate['repeated_station_timestamp_rows_beyond_first']}; conflicting rows: "
                f"{duplicate['repeated_station_timestamp_rows_with_level_different_from_first']}",
                f"- **Missing station identity rows:** "
                f"{dataset['station_coverage']['missing_identity_rows']}; "
                f"**malformed CSV rows:** {dataset['schema']['malformed_rows']}",
                f"- **Common intervals (minutes):** "
                f"`{json.dumps(intervals['common_whole_minute_intervals'][:5])}`",
                f"- **Minimum/maximum source rows:** "
                f"{level['minimum_record']['source_row_number'] if level['minimum_record'] else 'N/A'} / "
                f"{level['maximum_record']['source_row_number'] if level['maximum_record'] else 'N/A'}",
                f"- **Largest observed station gap:** "
                f"{intervals['largest_gaps'][0]['station_as_supplied']} "
                f"{intervals['largest_gaps'][0]['from']} to {intervals['largest_gaps'][0]['to']} "
                f"({intervals['largest_gaps'][0]['gap_hours']} hours)"
                if intervals["largest_gaps"]
                else "- **Largest observed station gap:** N/A",
                "",
                "| Column | Inferred lexical kind | Missing |",
                "|---|---|---:|",
                *[
                    f"| `{column['name']}` | {column['inferred_lexical_kind']} | "
                    f"{column['missing_values']} |"
                    for column in dataset["schema"]["columns"]
                ],
            ]
        )
    target = report["candidate_forecasting_target"]
    join = report["auxiliary_data_join_review"]
    lines.extend(
        [
            "",
            "## Target feasibility",
            "",
            f"**{target['status']}** — {target['candidate_definition']}",
            "",
            *[f"- {reason}" for reason in target["why_not_currently_justified"]],
            "",
            "## Rainfall/discharge joins",
            "",
            join.get("reason", "No approved source join is available."),
            (
                f"Existing processed-manifest context: {join.get('row_count')} rows; "
                f"rainfall missing {join.get('missing_values', {}).get('rainfall', 'unknown')}; "
                f"discharge missing {join.get('missing_values', {}).get('discharge', 'unknown')}; "
                f"`training_suitable={join.get('training_suitable')}`."
            ),
            "",
            "No join, resampling, imputation, normalization, or feature generation was performed.",
            "",
            "## Potential data leakage risks",
            "",
            *[
                f"- {risk}"
                for risk in report["datasets"][0]["potential_leakage_risks"]
            ],
            "",
            "## Leakage-resistant evaluation proposal",
            "",
            f"- **Split:** {report['evaluation_plan_if_later_approved']['split']}",
            f"- **Embargo:** {report['evaluation_plan_if_later_approved']['embargo']}",
            f"- **Station grouping:** {report['evaluation_plan_if_later_approved']['station_grouping']}",
            *[
                f"- {item}"
                for item in report["evaluation_plan_if_later_approved"]["baselines_and_metrics"]
            ],
            "",
            "## Interpretation",
            "",
            "This feasibility status concerns exploratory continuous water-level forecasting only. "
            "It does not establish a validated flood prediction, emergency-warning capability, or "
            "hydraulic-modelling readiness.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read-only profiling of hydrological CSVs for continuous water-level forecasting feasibility."
    )
    parser.add_argument("--files", nargs="+", type=Path, default=list(DEFAULT_FILES))
    parser.add_argument(
        "--processed-manifest", type=Path, default=PROCESSED_MANIFEST
    )
    parser.add_argument(
        "--json-report",
        type=Path,
        default=ROOT / "docs" / "STAGE_2_ML_PART_1_HYDROLOGICAL_FORECASTING_FEASIBILITY.json",
    )
    parser.add_argument(
        "--markdown-report",
        type=Path,
        default=ROOT / "docs" / "STAGE_2_ML_PART_1_HYDROLOGICAL_FORECASTING_FEASIBILITY.md",
    )
    args = parser.parse_args()
    report = build_report(tuple(args.files), processed_manifest=args.processed_manifest)
    args.json_report.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_report.parent.mkdir(parents=True, exist_ok=True)
    args.json_report.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    args.markdown_report.write_text(render_markdown(report), encoding="utf-8")
    print(f"Status: {report['overall_status']}")
    print(f"JSON report: {args.json_report}")
    print(f"Markdown report: {args.markdown_report}")


if __name__ == "__main__":
    main()
