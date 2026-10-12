import csv
import hashlib
import json

import pytest

from ml.preprocessing.historical_analytics import (
    build_historical_analytics,
    write_historical_analytics,
)


def _write_dataset(root, rows, *, columns=None):
    dataset_dir = root / "ml" / "datasets" / "historical_data" / "processed"
    source_dir = root / "ml" / "datasets" / "historical_disasters" / "EM-DAT"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    source_dir.mkdir(parents=True, exist_ok=True)
    source_path = source_dir / "source.xlsx"
    source_path.write_bytes(b"authorized test fixture")
    input_path = dataset_dir / "emdat_cleaned.csv"
    input_path.write_text("source fixture\n", encoding="utf-8")
    fields = columns or [
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
    ]
    dataset_path = dataset_dir / "floods.csv"
    with dataset_path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    digest = hashlib.sha256(dataset_path.read_bytes()).hexdigest()
    source_digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
    input_digest = hashlib.sha256(input_path.read_bytes()).hexdigest()
    manifest = {
        "dataset_name": "floods",
        "source_name": "EM-DAT test fixture",
        "source_reference": "test-only",
        "license": "test fixture only",
        "source_file": source_path.name,
        "source_sha256": source_digest,
        "processed_input_file": input_path.name,
        "processed_input_sha256": input_digest,
        "row_count": len(rows),
        "dataset_sha256": digest,
        "event_categories": ["Flood"],
        "target_definition": "Historical event classification only.",
        "validation": {"sha256": digest, "non_empty": bool(rows), "training_suitable": False},
    }
    (dataset_dir / "floods.manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return dataset_dir


def _event(event_id, year, *, latitude="", longitude="", event_date="", deaths="", affected="", damage=""):
    return {
        "disno.": event_id,
        "disaster_type": "Flood",
        "country": "Testland",
        "start_year": str(year),
        "start_date": event_date,
        "latitude": latitude,
        "longitude": longitude,
        "total_deaths": deaths,
        "total_affected": affected,
        "total_damage_'000_us$": damage,
    }


def test_analytics_preserve_missing_and_invalid_quality_without_dropping_events(tmp_path):
    _write_dataset(
        tmp_path,
        [
            _event("A", 2020, latitude="12.5", longitude="77.2", event_date="2020-01-02", deaths="3", affected="10", damage="2.5"),
            _event("B", 2021, latitude="invalid", longitude="", event_date="not-a-date"),
        ],
    )

    result = build_historical_analytics(tmp_path)
    dataset = result["dataset_inventory"][0]

    assert result["summary"]["unique_event_ids"] == 2
    assert result["summary"]["events_by_year"] == {"2020": 1, "2021": 1}
    assert dataset["date_coverage"]["invalid_start_dates"] == 1
    assert dataset["geography"]["rows_with_both_valid_coordinates"] == 1
    assert dataset["geography"]["invalid_coordinate_rows"] == 1
    assert dataset["duplicate_quality"] == {
        "exact_duplicate_rows": 0,
        "duplicate_event_id_rows": 0,
    }
    assert result["summary"]["reported_impacts"]["total_deaths"]["sum_of_reported_values"] == 3


def test_analytics_identify_exact_and_duplicate_event_rows_without_silent_deletion(tmp_path):
    duplicate = _event("A", 2020, event_date="2020-01-02", deaths="3")
    _write_dataset(tmp_path, [duplicate, duplicate.copy()])

    result = build_historical_analytics(tmp_path)
    quality = result["dataset_inventory"][0]["duplicate_quality"]

    assert quality["exact_duplicate_rows"] == 1
    assert quality["duplicate_event_id_rows"] == 1
    assert result["summary"]["source_rows_across_extracts"] == 2
    assert result["summary"]["unique_event_ids"] == 1


def test_analytics_reject_missing_required_columns_and_corrupt_manifest(tmp_path):
    _write_dataset(
        tmp_path,
        [{"event_id": "A", "disaster_type": "Flood"}],
        columns=["event_id", "disaster_type"],
    )
    with pytest.raises(ValueError, match="missing required columns"):
        build_historical_analytics(tmp_path)

    manifest_path = tmp_path / "ml" / "datasets" / "historical_data" / "processed" / "floods.manifest.json"
    manifest_path.write_text("{not-json", encoding="utf-8")
    with pytest.raises(ValueError, match="Cannot read dataset manifest"):
        build_historical_analytics(tmp_path)


def test_analytics_export_is_reproducible_and_has_input_and_output_hashes(tmp_path):
    _write_dataset(tmp_path, [_event("A", 2020, event_date="2020-01-02")])
    output_path = tmp_path / "derived" / "analytics.json"

    first = write_historical_analytics(tmp_path, output_path)
    first_bytes = output_path.read_bytes()
    second = write_historical_analytics(tmp_path, output_path)

    assert output_path.read_bytes() == first_bytes
    assert first["manifest"] == second["manifest"]
    assert first["manifest"]["source_rows_scanned"] == 1
    assert first["manifest"]["rejected_rows"] == 0
    assert first["manifest"]["output_sha256"] == hashlib.sha256(first_bytes).hexdigest()
    assert output_path.with_suffix(".manifest.json").is_file()
