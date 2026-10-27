from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

from ml.preprocessing.file_integrity import sha256_file

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATASETS_DIR = PROJECT_ROOT / "ml" / "datasets" / "historical_data" / "processed"
EMDAT_DIR = PROJECT_ROOT / "ml" / "datasets" / "historical_disasters" / "EM-DAT"
DEFAULT_OUTPUT = PROJECT_ROOT / "ml" / "datasets" / "historical_data" / "analytics" / "historical_analytics.json"
TRANSFORMATION_VERSION = "emdat-historical-analytics-v1"
REQUIRED_COLUMNS = {
    "disno.",
    "disaster_type",
    "country",
    "start_year",
    "latitude",
    "longitude",
    "total_deaths",
    "total_affected",
}
IMPACT_COLUMNS = (
    ("total_deaths", "people"),
    ("total_affected", "people"),
    ("total_damage_'000_us$", "thousand source-reported US dollars"),
)
MISSING_VALUES = {"", "na", "n/a", "null", "none", "-"}


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
    missing_counts = {column: 0 for column in columns}
    column_values = {column: [] for column in columns}
    with_coordinates = 0
    invalid_coordinates = 0
    valid_dates: list[date] = []
    invalid_dates = 0
    for row in rows:
        row_key = tuple(row[column] for column in columns)
        if row_key in seen_rows:
            exact_duplicates += 1
        seen_rows.add(row_key)
        event_id = row["disno."].strip()
        if event_id in seen_event_ids:
            duplicate_event_ids += 1
        seen_event_ids.add(event_id)
        for column in columns:
            value = row[column]
            if _is_missing(value):
                missing_counts[column] += 1
            column_values[column].append(value)

        latitude = _number(row["latitude"])
        longitude = _number(row["longitude"])
        if latitude is not None and longitude is not None:
            if -90 <= latitude <= 90 and -180 <= longitude <= 180:
                with_coordinates += 1
            else:
                invalid_coordinates += 1
        elif not _is_missing(row["latitude"]) or not _is_missing(row["longitude"]):
            invalid_coordinates += 1

        raw_date = row.get("start_date", "").strip()
        if raw_date and raw_date.casefold() not in MISSING_VALUES:
            try:
                valid_dates.append(date.fromisoformat(raw_date[:10]))
            except ValueError:
                invalid_dates += 1

    inventory = {
        "name": manifest.get("dataset_name", manifest_path.stem.removesuffix(".manifest")),
        "path": str(dataset_path.relative_to(PROJECT_ROOT)) if dataset_path.is_relative_to(PROJECT_ROOT) else str(dataset_path),
        "manifest": str(manifest_path.relative_to(PROJECT_ROOT)) if manifest_path.is_relative_to(PROJECT_ROOT) else str(manifest_path),
        "source_name": manifest.get("source_name"),
        "source_reference": manifest.get("source_reference"),
        "license": manifest.get("license"),
        "source_file": source_path.name,
        "source_sha256": manifest.get("source_sha256"),
        "processed_input_file": input_path.name,
        "processed_input_sha256": manifest.get("processed_input_sha256"),
        "sha256": dataset_hash,
        "rows": len(rows),
        "columns": columns,
        "data_types": {column: _type_name(column_values[column]) for column in columns},
        "date_coverage": {
            "start": min(valid_dates).isoformat() if valid_dates else None,
            "end": max(valid_dates).isoformat() if valid_dates else None,
            "valid_start_dates": len(valid_dates),
            "invalid_start_dates": invalid_dates,
            "rows_with_start_year": len(rows) - missing_counts.get("start_year", len(rows)),
        },
        "geography": {
            "unique_countries": len({row["country"].strip() for row in rows if not _is_missing(row["country"])}),
            "rows_with_both_valid_coordinates": with_coordinates,
            "coordinate_coverage_percent": round(with_coordinates / len(rows) * 100, 2) if rows else 0,
            "invalid_coordinate_rows": invalid_coordinates,
        },
        "missing_percent": {
            column: round(count / len(rows) * 100, 2)
            for column, count in missing_counts.items()
            if count
        },
        "duplicate_quality": {
            "exact_duplicate_rows": exact_duplicates,
            "duplicate_event_id_rows": duplicate_event_ids,
        },
        "event_categories": manifest.get("event_categories", []),
        "target_definition": manifest.get("target_definition"),
        "training_suitable": validation.get("training_suitable", False),
        "manifest_validation": "VALIDATED",
    }
    return inventory, rows


def build_historical_analytics(project_root: str | Path = PROJECT_ROOT) -> dict[str, Any]:
    """Build deterministic, provenance-checked aggregates from existing EM-DAT extracts."""
    root = Path(project_root).resolve()
    datasets_dir = root / "ml" / "datasets" / "historical_data" / "processed"
    emdat_dir = root / "ml" / "datasets" / "historical_disasters" / "EM-DAT"
    manifests = sorted(datasets_dir.glob("*.manifest.json"))
    if not manifests:
        raise ValueError(f"No validated historical dataset manifests found in {datasets_dir}.")

    inventory: list[dict[str, Any]] = []
    event_by_id: dict[str, dict[str, str]] = {}
    categories_by_event: dict[str, set[str]] = defaultdict(set)
    event_ids_by_year: dict[str, set[str]] = defaultdict(set)
    event_ids_by_type: dict[str, set[str]] = defaultdict(set)
    event_ids_by_country: dict[str, set[str]] = defaultdict(set)
    impact_values: dict[str, dict[str, float]] = {
        column: {"reported_records": 0, "sum": 0.0}
        for column, _unit in IMPACT_COLUMNS
    }

    for manifest_path in manifests:
        dataset, rows = _load_dataset(manifest_path, datasets_dir=datasets_dir, emdat_dir=emdat_dir)
        inventory.append(dataset)
        category = manifest_path.name.removesuffix(".manifest.json")
        for row in rows:
            event_id = row["disno."].strip()
            if not event_id:
                continue
            categories_by_event[event_id].add(category)
            if event_id not in event_by_id:
                event_by_id[event_id] = row

    for event_id, row in event_by_id.items():
        year = row.get("start_year", "").strip()
        if year and year.isdigit():
            event_ids_by_year[year].add(event_id)
        disaster_type = row.get("disaster_type", "").strip()
        country = row.get("country", "").strip()
        if not _is_missing(disaster_type):
            event_ids_by_type[disaster_type].add(event_id)
        if not _is_missing(country):
            event_ids_by_country[country].add(event_id)
        for column, _unit in IMPACT_COLUMNS:
            amount = _number(row.get(column))
            if amount is not None and amount >= 0:
                impact_values[column]["reported_records"] += 1
                impact_values[column]["sum"] += amount

    overlapping_events = {
        event_id: sorted(categories)
        for event_id, categories in categories_by_event.items()
        if len(categories) > 1
    }
    return {
        "analytics_version": TRANSFORMATION_VERSION,
        "status": "READY",
        "source": "EM-DAT event and impact records; not environmental measurements or forecasts.",
        "dataset_inventory": inventory,
        "summary": {
            "source_rows_across_extracts": sum(dataset["rows"] for dataset in inventory),
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
                    key=lambda item: (-len(item[1]), item[0]),
                )
            ],
            "reported_impacts": {
                column: {
                    "reported_records": int(values["reported_records"]),
                    "sum_of_reported_values": round(values["sum"], 3),
                    "unit": next(unit for impact_column, unit in IMPACT_COLUMNS if impact_column == column),
                    "interpretation": "Descriptive sum of non-missing source reports; coverage is incomplete.",
                }
                for column, values in impact_values.items()
            },
            "data_quality": {
                "exact_duplicate_rows": sum(item["duplicate_quality"]["exact_duplicate_rows"] for item in inventory),
                "duplicate_event_id_rows_within_extracts": sum(
                    item["duplicate_quality"]["duplicate_event_id_rows"] for item in inventory
                ),
                "event_ids_shared_between_extracts": len(overlapping_events),
                "event_ids_shared_between_extracts_sample": {
                    event_id: categories for event_id, categories in sorted(overlapping_events.items())[:50]
                },
                "rows_with_valid_coordinates": sum(
                    item["geography"]["rows_with_both_valid_coordinates"] for item in inventory
                ),
                "rows_missing_or_without_a_valid_coordinate_pair": sum(
                    item["rows"] - item["geography"]["rows_with_both_valid_coordinates"]
                    for item in inventory
                ),
            },
        },
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
        ],
    }


def write_historical_analytics(
    project_root: str | Path = PROJECT_ROOT,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    output = Path(output_path).resolve() if output_path else (root / DEFAULT_OUTPUT.relative_to(PROJECT_ROOT))
    summary = build_historical_analytics(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(summary, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    source_hashes = {
        dataset["path"]: dataset["sha256"]
        for dataset in summary["dataset_inventory"]
    }
    manifest = {
        "manifest_version": "1.0",
        "transformation_version": TRANSFORMATION_VERSION,
        "source_files": source_hashes,
        "source_rows_scanned": summary["summary"]["source_rows_across_extracts"],
        "unique_event_ids": summary["summary"]["unique_event_ids"],
        "rejected_rows": 0,
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
