from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any

from ml.preprocessing.file_integrity import sha256_file

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATASETS_DIR = PROJECT_ROOT / "ml" / "datasets" / "historical_data" / "processed"
EMDAT_DIR = PROJECT_ROOT / "ml" / "datasets" / "historical_disasters" / "EM-DAT"
DEFAULT_OUTPUT = PROJECT_ROOT / "ml" / "datasets" / "historical_data" / "analytics" / "historical_analytics.json"
TRANSFORMATION_VERSION = "emdat-historical-analytics-v2"
REQUIRED_COLUMNS = {
    "disno.",
    "disaster_type",
    "country",
    "start_year",
    "start_date",
    "latitude",
    "longitude",
    "total_deaths",
    "total_affected",
    "total_damage_'000_us$",
}
IMPACT_COLUMNS = (
    ("total_deaths", "people"),
    ("total_affected", "people"),
    ("total_damage_'000_us$", "thousand source-reported US dollars"),
)
IMPACT_LABELS = {
    "total_deaths": "Reported deaths",
    "total_affected": "Reported total affected",
    "total_damage_'000_us$": "Reported total damage",
}
MISSING_VALUES = {"", "na", "n/a", "null", "none", "-", "nan"}


def _sha256(path: Path) -> str:
    return sha256_file(path)


def _is_missing(value: Any) -> bool:
    return value is None or str(value).strip().casefold() in MISSING_VALUES


def _number(value: Any) -> float | None:
    if _is_missing(value):
        return None
    try:
        number = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _parsed_date(value: Any) -> date | None:
    if _is_missing(value):
        return None
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return None


def _impact_value(value: Any) -> tuple[float | None, str]:
    if _is_missing(value):
        return None, "missing"
    number = _number(value)
    if number is None:
        return None, "invalid"
    if number < 0:
        return None, "negative"
    return number, "reported"


def _type_name(values: list[str]) -> str:
    non_missing = [value for value in values if not _is_missing(value)]
    if not non_missing:
        return "unknown"
    numbers = [_number(value) for value in non_missing]
    if all(value is not None for value in numbers):
        return "integer" if all(float(value).is_integer() for value in numbers if value is not None) else "number"
    return "string"


def _safe_child(root: Path, filename: Any, label: str) -> Path:
    name = str(filename or "")
    if not name or Path(name).name != name:
        raise ValueError(f"{label} must be a filename relative to its dataset directory.")
    return root / name


def _load_dataset(
    manifest_path: Path,
    *,
    datasets_dir: Path,
    emdat_dir: Path,
    as_of_date: date,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Cannot read dataset manifest {manifest_path.name}: {error}") from error
    if not isinstance(manifest, dict):
        raise ValueError(f"Dataset manifest {manifest_path.name} must contain a JSON object.")
    validation = manifest.get("validation")
    if not isinstance(validation, dict):
        raise ValueError(f"Dataset manifest {manifest_path.name} must include a validation object.")

    dataset_path = _safe_child(datasets_dir, manifest_path.name.removesuffix(".manifest.json") + ".csv", "Dataset path")
    if not dataset_path.is_file():
        raise ValueError(f"Dataset CSV is missing: {dataset_path.name}.")
    dataset_hash = sha256_file(dataset_path, normalize_csv_line_endings=True)
    if manifest.get("dataset_sha256") != dataset_hash:
        raise ValueError(f"Dataset SHA-256 does not match {manifest_path.name}.")
    if validation.get("sha256") != dataset_hash:
        raise ValueError(f"Validation SHA-256 does not match {manifest_path.name}.")

    source_path = _safe_child(emdat_dir, manifest.get("source_file"), "Source workbook")
    if not source_path.is_file() or _sha256(source_path) != manifest.get("source_sha256"):
        raise ValueError(f"Source workbook is missing or its SHA-256 does not match {manifest_path.name}.")
    input_path = _safe_child(datasets_dir, manifest.get("processed_input_file"), "Processed input")
    if not input_path.is_file() or _sha256(input_path) != manifest.get("processed_input_sha256"):
        raise ValueError(f"Processed input is missing or its SHA-256 does not match {manifest_path.name}.")

    rows: list[dict[str, str]] = []
    with dataset_path.open(encoding="utf-8-sig", newline="") as dataset_file:
        reader = csv.DictReader(dataset_file)
        if reader.fieldnames is None:
            raise ValueError(f"Dataset {dataset_path.name} has no CSV header.")
        missing_columns = REQUIRED_COLUMNS - set(reader.fieldnames)
        if missing_columns:
            raise ValueError(
                f"Dataset {dataset_path.name} is missing required columns: {', '.join(sorted(missing_columns))}."
            )
        columns = list(reader.fieldnames)
        for row in reader:
            if None in row:
                raise ValueError(f"Dataset {dataset_path.name} contains a row with more values than its header.")
            rows.append({column: row.get(column, "") or "" for column in columns})

    if len(rows) != manifest.get("row_count"):
        raise ValueError(
            f"Dataset row count does not match {manifest_path.name}: "
            f"manifest={manifest.get('row_count')}, actual={len(rows)}."
        )
    if validation.get("non_empty") is not True or not rows:
        raise ValueError(f"Dataset {dataset_path.name} is empty or not marked as non-empty.")

    seen_rows: set[tuple[str, ...]] = set()
    seen_event_ids: set[str] = set()
    exact_duplicates = 0
    duplicate_event_ids = 0
    missing_event_ids = 0
    missing_country_rows = 0
    missing_counts = {column: 0 for column in columns}
    column_values = {column: [] for column in columns}
    with_coordinates = 0
    partial_coordinates = 0
    invalid_coordinates = 0
    missing_latitude = 0
    missing_longitude = 0
    valid_dates: list[date] = []
    missing_dates = 0
    invalid_dates = 0
    future_dates = 0
    missing_start_year = 0
    start_year_mismatches = 0
    missing_end_dates = 0
    invalid_end_dates = 0
    end_before_start = 0
    impacts = {
        column: {
            "reported_records": 0,
            "missing_records": 0,
            "invalid_records": 0,
            "negative_records": 0,
            "explicit_zero_records": 0,
            "sum_of_reported_values": 0.0,
        }
        for column, _unit in IMPACT_COLUMNS
    }
    disaster_type_counts: Counter[str] = Counter()
    for row in rows:
        row_key = tuple(row[column] for column in columns)
        if row_key in seen_rows:
            exact_duplicates += 1
        seen_rows.add(row_key)
        event_id = row["disno."].strip()
        if not event_id:
            missing_event_ids += 1
        elif event_id in seen_event_ids:
            duplicate_event_ids += 1
        else:
            seen_event_ids.add(event_id)
        if _is_missing(row["country"]):
            missing_country_rows += 1
        if not _is_missing(row["disaster_type"]):
            disaster_type_counts[row["disaster_type"].strip()] += 1
        for column in columns:
            value = row[column]
            if _is_missing(value):
                missing_counts[column] += 1
            column_values[column].append(value)

        latitude_missing = _is_missing(row["latitude"])
        longitude_missing = _is_missing(row["longitude"])
        missing_latitude += int(latitude_missing)
        missing_longitude += int(longitude_missing)
        latitude = None if latitude_missing else _number(row["latitude"])
        longitude = None if longitude_missing else _number(row["longitude"])
        latitude_invalid = not latitude_missing and (
            latitude is None or latitude < -90 or latitude > 90
        )
        longitude_invalid = not longitude_missing and (
            longitude is None or longitude < -180 or longitude > 180
        )
        if latitude_missing != longitude_missing:
            partial_coordinates += 1
        if latitude_invalid or longitude_invalid:
            invalid_coordinates += 1
        if (
            not latitude_missing
            and not longitude_missing
            and not latitude_invalid
            and not longitude_invalid
        ):
            with_coordinates += 1

        start_date = _parsed_date(row.get("start_date"))
        if _is_missing(row.get("start_date")):
            missing_dates += 1
        elif start_date is None:
            invalid_dates += 1
        else:
            valid_dates.append(start_date)
            future_dates += int(start_date > as_of_date)
            raw_year = row.get("start_year", "").strip()
            if not raw_year or not raw_year.isdigit():
                missing_start_year += 1
            elif int(raw_year) != start_date.year:
                start_year_mismatches += 1

        end_date = _parsed_date(row.get("end_date"))
        if _is_missing(row.get("end_date")):
            missing_end_dates += 1
        elif end_date is None:
            invalid_end_dates += 1
        elif start_date is not None and end_date < start_date:
            end_before_start += 1

        for column, _unit in IMPACT_COLUMNS:
            amount, quality = _impact_value(row.get(column))
            if quality == "reported":
                impacts[column]["reported_records"] += 1
                impacts[column]["sum_of_reported_values"] += amount or 0
                impacts[column]["explicit_zero_records"] += int(amount == 0)
            elif quality == "missing":
                impacts[column]["missing_records"] += 1
            elif quality == "negative":
                impacts[column]["negative_records"] += 1
            else:
                impacts[column]["invalid_records"] += 1

    inventory = {
        "name": manifest.get("dataset_name", manifest_path.stem.removesuffix(".manifest")),
        "dataset_file": dataset_path.name,
        "source_name": manifest.get("source_name"),
        "source_reference": manifest.get("source_reference"),
        "license": manifest.get("license"),
        "source_file": source_path.name,
        "source_sha256": manifest.get("source_sha256"),
        "processed_input_file": input_path.name,
        "processed_input_sha256": manifest.get("processed_input_sha256"),
        "sha256": dataset_hash,
        "rows": len(rows),
        "unique_event_count": len(seen_event_ids),
        "columns": columns,
        "data_types": {column: _type_name(column_values[column]) for column in columns},
        "disaster_type_counts": dict(sorted(disaster_type_counts.items())),
        "missing_event_ids": missing_event_ids,
        "missing_country_rows": missing_country_rows,
        "unique_event_ids": len(seen_event_ids),
        "date_coverage": {
            "start": min(valid_dates).isoformat() if valid_dates else None,
            "end": max(valid_dates).isoformat() if valid_dates else None,
            "valid_start_dates": len(valid_dates),
            "missing_start_dates": missing_dates,
            "invalid_start_dates": invalid_dates,
            "future_start_dates": future_dates,
            "as_of_date": as_of_date.isoformat(),
            "missing_start_year": missing_start_year,
            "start_year_mismatches": start_year_mismatches,
            "parseable_end_dates": len(rows) - missing_end_dates - invalid_end_dates,
            "missing_end_dates": missing_end_dates,
            "invalid_end_dates": invalid_end_dates,
            "end_before_start": end_before_start,
        },
        "geography": {
            "unique_countries": len({row["country"].strip() for row in rows if not _is_missing(row["country"])}),
            "missing_country_rows": missing_country_rows,
            "rows_with_both_valid_coordinates": with_coordinates,
            "coordinate_coverage_denominator": len(rows),
            "coordinate_coverage_percent": round(with_coordinates / len(rows) * 100, 2) if rows else 0,
            "missing_latitude": missing_latitude,
            "missing_longitude": missing_longitude,
            "rows_with_partial_coordinates": partial_coordinates,
            "invalid_coordinate_rows": invalid_coordinates,
        },
        "impact_coverage": {
            column: {
                **values,
                "denominator_records": len(rows),
                "coverage_percent": round(values["reported_records"] / len(rows) * 100, 2) if rows else 0,
                "sum_of_reported_values": round(values["sum_of_reported_values"], 3),
                "unit": unit,
                "label": IMPACT_LABELS[column],
            }
            for column, unit in IMPACT_COLUMNS
            for values in [impacts[column]]
        },
        "missing_percent": {
            column: round(count / len(rows) * 100, 2)
            for column, count in missing_counts.items()
            if count
        },
        "missing_value_counts": {
            column: count
            for column, count in missing_counts.items()
            if count
        },
        "duplicate_quality": {
            "exact_duplicate_rows": exact_duplicates,
            "duplicate_event_id_rows": duplicate_event_ids,
        },
        "event_categories": manifest.get("event_categories", []),
        "classification_field": "disaster_type",
        "year_aggregation_exclusions": {
            "missing_start_date": missing_dates,
            "invalid_start_date": invalid_dates,
            "future_start_date": future_dates,
            "end_before_start": end_before_start,
            "missing_event_id": missing_event_ids,
        },
        "target_definition": manifest.get("target_definition"),
        "training_suitable": validation.get("training_suitable", False),
        "manifest_validation": "VALIDATED",
        "warnings": [
            warning
            for condition, warning in (
                (future_dates > 0, f"{future_dates} start date(s) occur after the validation date."),
                (end_before_start > 0, f"{end_before_start} end date(s) precede their start date."),
                (missing_dates > 0, f"{missing_dates} row(s) have no start date."),
                (invalid_dates > 0, f"{invalid_dates} row(s) have an invalid start date."),
                (with_coordinates < len(rows), "Coordinates are incomplete for some or all event rows."),
            )
            if condition
        ],
    }
    return inventory, rows


def build_historical_analytics(
    project_root: str | Path = PROJECT_ROOT,
    *,
    as_of_date: date | None = None,
) -> dict[str, Any]:
    """Build deterministic, provenance-checked aggregates from existing EM-DAT extracts."""
    root = Path(project_root).resolve()
    validation_date = as_of_date or date.today()
    datasets_dir = root / "ml" / "datasets" / "historical_data" / "processed"
    emdat_dir = root / "ml" / "datasets" / "historical_disasters" / "EM-DAT"
    manifests = sorted(datasets_dir.glob("*.manifest.json"))
    if not manifests:
        raise ValueError("No historical dataset manifests were found.")

    inventory: list[dict[str, Any]] = []
    event_by_id: dict[str, dict[str, str]] = {}
    categories_by_event: dict[str, set[str]] = defaultdict(set)
    event_ids_by_year: dict[str, set[str]] = defaultdict(set)
    event_ids_by_type: dict[str, set[str]] = defaultdict(set)
    event_ids_by_country: dict[str, set[str]] = defaultdict(set)
    impact_values: dict[str, dict[str, float | int]] = {
        column: {
            "reported_records": 0,
            "missing_records": 0,
            "invalid_records": 0,
            "negative_records": 0,
            "explicit_zero_records": 0,
            "sum": 0.0,
        }
        for column, _unit in IMPACT_COLUMNS
    }

    for manifest_path in manifests:
        try:
            dataset, rows = _load_dataset(
                manifest_path,
                datasets_dir=datasets_dir,
                emdat_dir=emdat_dir,
                as_of_date=validation_date,
            )
        except (OSError, ValueError, TypeError, AttributeError) as error:
            message = str(error).replace(str(root), "<project>").replace(str(datasets_dir), "<datasets>").replace(str(emdat_dir), "<sources>")
            inventory.append({
                "name": manifest_path.name.removesuffix(".manifest.json"),
                "dataset_file": manifest_path.name.removesuffix(".manifest.json") + ".csv",
                "rows": None,
                "manifest_validation": "ERROR",
                "error": message,
                "warnings": [],
            })
            continue
        inventory.append(dataset)
        category = dataset["name"]
        for row in rows:
            event_id = row["disno."].strip()
            if not event_id:
                continue
            categories_by_event[event_id].add(category)
            if event_id not in event_by_id:
                event_by_id[event_id] = row

    for event_id, row in event_by_id.items():
        start_date = _parsed_date(row.get("start_date"))
        end_date = _parsed_date(row.get("end_date"))
        if (
            start_date is not None
            and start_date <= validation_date
            and not (end_date is not None and end_date < start_date)
        ):
            event_ids_by_year[str(start_date.year)].add(event_id)
        disaster_type = row.get("disaster_type", "").strip()
        country = row.get("country", "").strip()
        if not _is_missing(disaster_type):
            event_ids_by_type[disaster_type].add(event_id)
        if not _is_missing(country):
            event_ids_by_country[country].add(event_id)
        for column, _unit in IMPACT_COLUMNS:
            amount, quality = _impact_value(row.get(column))
            if quality == "reported":
                impact_values[column]["reported_records"] += 1
                impact_values[column]["sum"] += amount or 0
                impact_values[column]["explicit_zero_records"] += int(amount == 0)
            elif quality == "missing":
                impact_values[column]["missing_records"] += 1
            elif quality == "negative":
                impact_values[column]["negative_records"] += 1
            else:
                impact_values[column]["invalid_records"] += 1

    overlapping_events = {
        event_id: sorted(categories)
        for event_id, categories in categories_by_event.items()
        if len(categories) > 1
    }
    validated_datasets = [item for item in inventory if item["manifest_validation"] == "VALIDATED"]
    failed_datasets = [item for item in inventory if item["manifest_validation"] != "VALIDATED"]
    event_date_missing = sum(item["date_coverage"]["missing_start_dates"] for item in validated_datasets)
    event_date_invalid = sum(item["date_coverage"]["invalid_start_dates"] for item in validated_datasets)
    event_date_future = sum(item["date_coverage"]["future_start_dates"] for item in validated_datasets)
    chronology_errors = sum(item["date_coverage"]["end_before_start"] for item in validated_datasets)
    missing_event_ids = sum(item["missing_event_ids"] for item in validated_datasets)
    complete_validation = not failed_datasets
    analytics_status = "READY" if complete_validation else "PARTIAL" if validated_datasets else "ERROR"
    return {
        "analytics_version": TRANSFORMATION_VERSION,
        "status": analytics_status,
        "as_of_date": validation_date.isoformat(),
        "source": "EM-DAT event and impact records; not environmental measurements or forecasts.",
        "dataset_inventory": inventory,
        "summary": {
            "source_rows_across_extracts": sum(dataset["rows"] or 0 for dataset in validated_datasets),
            "unique_event_ids": len(event_by_id),
            "event_ids_present_in_multiple_extracts": len(overlapping_events),
            "events_by_year": {
                year: len(event_ids)
                for year, event_ids in sorted(event_ids_by_year.items(), key=lambda item: int(item[0]))
            },
            "events_by_disaster_type": {
                disaster_type: len(event_ids)
                for disaster_type, event_ids in sorted(event_ids_by_type.items())
            },
            "events_by_country": [
                {"country": country, "count": len(event_ids)}
                for country, event_ids in sorted(
                    event_ids_by_country.items(),
                    key=lambda item: (-len(item[1]), item[0].casefold(), item[0]),
                )
            ],
            "reported_impacts": {
                column: {
                    "reported_records": int(values["reported_records"]),
                    "missing_records": int(values["missing_records"]),
                    "invalid_records": int(values["invalid_records"]),
                    "negative_records": int(values["negative_records"]),
                    "explicit_zero_records": int(values["explicit_zero_records"]),
                    "coverage_percent": round(
                        int(values["reported_records"]) / len(event_by_id) * 100,
                        2,
                    ) if event_by_id else 0,
                    "sum_of_reported_values": round(values["sum"], 3),
                    "unit": next(unit for impact_column, unit in IMPACT_COLUMNS if impact_column == column),
                    "label": IMPACT_LABELS[column],
                    "source_field": column,
                    "interpretation": (
                        "Descriptive sum of valid non-negative source reports across unique event IDs; "
                        "missing or invalid values are not interpreted as zero."
                    ),
                }
                for column, values in impact_values.items()
            },
            "year_aggregation": {
                "date_field": "start_date",
                "description": "Unique event IDs grouped by valid start_date year.",
                "included_events": sum(len(ids) for ids in event_ids_by_year.values()),
                "excluded_events_total": len(event_by_id) - sum(
                    len(ids) for ids in event_ids_by_year.values()
                ),
                "excluded_missing_start_date": event_date_missing,
                "excluded_invalid_start_date": event_date_invalid,
                "excluded_future_start_date": event_date_future,
                "excluded_end_before_start": chronology_errors,
                "excluded_missing_event_id": missing_event_ids,
            },
            "data_quality": {
                "exact_duplicate_rows": sum(item["duplicate_quality"]["exact_duplicate_rows"] for item in validated_datasets),
                "duplicate_event_id_rows_within_extracts": sum(
                    item["duplicate_quality"]["duplicate_event_id_rows"] for item in validated_datasets
                ),
                "missing_event_id_rows": missing_event_ids,
                "missing_country_rows": sum(item["missing_country_rows"] for item in validated_datasets),
                "event_ids_shared_between_extracts": len(overlapping_events),
                "event_ids_shared_between_extracts_sample": {
                    event_id: categories for event_id, categories in sorted(overlapping_events.items())[:50]
                },
                "rows_with_valid_coordinates": sum(
                    item["geography"]["rows_with_both_valid_coordinates"] for item in validated_datasets
                ),
                "rows_missing_or_without_a_valid_coordinate_pair": sum(
                    item["rows"] - item["geography"]["rows_with_both_valid_coordinates"]
                    for item in validated_datasets
                ),
            },
        },
        "validation_errors": [
            {"dataset": item["name"], "error": item["error"]}
            for item in failed_datasets
        ],
        "capabilities": {
            "historical_descriptive_analytics": "SUPPORTED",
            "historical_flood_event_counts": "SUPPORTED_WITH_EMDAT_CLASSIFICATION_AND_COVERAGE_LIMITATIONS",
            "flood_event_classification": "NOT_SUPPORTED_NO_VALIDATED_NEGATIVE_EXAMPLES_OR_PREDICTION_UNIT",
            "environmental_flood_prediction": "NOT_SUPPORTED_NO_JOINED_VERIFIED_LABELS_AND_INFERENCE_FEATURES",
        },
        "limitations": [
            "EM-DAT records are reported event/impact records and are not proof of complete event or no-event surveillance.",
            "Missing event coordinates prevent site-level joins for many records; unlocated rows remain in country/year analytics only.",
            "Missing impact fields mean reported-impact sums are not complete totals.",
            "Flood event records do not provide a continuous flood-risk or calibrated probability target.",
            "EM-DAT redistribution is subject to the access terms of the supplied academic/research request.",
            "Year counts include only unique events with valid, non-future start dates and no start/end chronology conflict.",
        ],
    }


def write_historical_analytics(
    project_root: str | Path = PROJECT_ROOT,
    output_path: str | Path | None = None,
    *,
    as_of_date: date | None = None,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    output = Path(output_path).resolve() if output_path else (root / DEFAULT_OUTPUT.relative_to(PROJECT_ROOT))
    summary = build_historical_analytics(root, as_of_date=as_of_date)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(summary, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    source_hashes = {
        dataset["dataset_file"]: dataset["sha256"]
        for dataset in summary["dataset_inventory"]
        if dataset.get("manifest_validation") == "VALIDATED"
    }
    manifest = {
        "manifest_version": "1.0",
        "transformation_version": TRANSFORMATION_VERSION,
        "as_of_date": summary["as_of_date"],
        "source_files": source_hashes,
        "source_rows_scanned": summary["summary"]["source_rows_across_extracts"],
        "unique_event_ids": summary["summary"]["unique_event_ids"],
        "year_aggregation_excluded_events": summary["summary"]["year_aggregation"]["excluded_events_total"],
        "year_aggregation_exclusions": summary["summary"]["year_aggregation"],
        "failed_datasets": len(summary["validation_errors"]),
        "rejected_rows": sum(
            item.get("rows", 0) or 0
            for item in summary["dataset_inventory"]
            if item.get("manifest_validation") != "VALIDATED"
        ),
        "output_file": output.name,
        "output_sha256": _sha256(output),
        "deterministic_output": True,
    }
    output.with_suffix(".manifest.json").write_text(
        json.dumps(manifest, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return {"summary": summary, "manifest": manifest, "output_path": str(output)}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate and aggregate existing EM-DAT extracts without modifying source datasets."
    )
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--output", type=Path, default=None)
    arguments = parser.parse_args()
    result = write_historical_analytics(arguments.project_root, arguments.output)
    print(json.dumps({
        "output_path": result["output_path"],
        "rows_scanned": result["manifest"]["source_rows_scanned"],
        "unique_event_ids": result["manifest"]["unique_event_ids"],
        "output_sha256": result["manifest"]["output_sha256"],
    }, indent=2))


if __name__ == "__main__":
    main()
