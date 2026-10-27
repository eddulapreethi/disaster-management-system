import csv
import hashlib
import json
from datetime import date

from ml.preprocessing.file_integrity import sha256_file
from ml.preprocessing.historical_analytics import (
    build_historical_analytics,
    write_historical_analytics,
)


def _write_dataset(root, rows, *, columns=None, dataset_name="floods"):
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
        "end_date",
        "latitude",
        "longitude",
        "total_deaths",
        "total_affected",
        "total_damage_'000_us$",
    ]
    dataset_path = dataset_dir / f"{dataset_name}.csv"
    with dataset_path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    digest = sha256_file(dataset_path, normalize_csv_line_endings=True)
    source_digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
    input_digest = sha256_file(input_path)
    manifest = {
        "dataset_name": dataset_name,
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
    (dataset_dir / f"{dataset_name}.manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return dataset_dir


def _event(
    event_id,
    year,
    *,
    country="Testland",
    latitude="",
    longitude="",
    event_date="",
    end_date="",
    deaths="",
    affected="",
    damage="",
):
    return {
        "disno.": event_id,
        "disaster_type": "Flood",
        "country": country,
        "start_year": str(year),
        "start_date": event_date,
        "end_date": end_date,
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
    assert result["summary"]["events_by_year"] == {"2020": 1}
    assert dataset["date_coverage"]["invalid_start_dates"] == 1
    assert dataset["date_coverage"]["missing_start_dates"] == 0
    assert dataset["geography"]["rows_with_both_valid_coordinates"] == 1
    assert dataset["geography"]["invalid_coordinate_rows"] == 1
    assert dataset["duplicate_quality"] == {
        "exact_duplicate_rows": 0,
        "duplicate_event_id_rows": 0,
    }
    assert result["summary"]["reported_impacts"]["total_deaths"]["sum_of_reported_values"] == 3
    assert result["summary"]["year_aggregation"]["excluded_invalid_start_date"] == 1


def test_analytics_identify_exact_and_duplicate_event_rows_without_silent_deletion(tmp_path):
    duplicate = _event("A", 2020, event_date="2020-01-02", deaths="3")
    _write_dataset(tmp_path, [duplicate, duplicate.copy()])

    result = build_historical_analytics(tmp_path)
    quality = result["dataset_inventory"][0]["duplicate_quality"]

    assert quality["exact_duplicate_rows"] == 1
    assert quality["duplicate_event_id_rows"] == 1
    assert result["summary"]["source_rows_across_extracts"] == 2
    assert result["summary"]["unique_event_ids"] == 1


def test_cross_extract_overlap_is_reported_but_rows_are_not_removed(tmp_path):
    dataset_dir = _write_dataset(
        tmp_path,
        [_event("SHARED", 2020, event_date="2020-01-01")],
        dataset_name="floods",
    )
    _write_dataset(
        tmp_path,
        [_event("SHARED", 2020, event_date="2020-01-01")],
        dataset_name="earthquakes",
    )

    result = build_historical_analytics(tmp_path, as_of_date=date(2026, 10, 27))

    assert result["summary"]["source_rows_across_extracts"] == 2
    assert result["summary"]["unique_event_ids"] == 1
    assert result["summary"]["event_ids_present_in_multiple_extracts"] == 1
    assert result["summary"]["data_quality"]["event_ids_shared_between_extracts_sample"] == {
        "SHARED": ["earthquakes", "floods"],
    }


def test_missing_event_ids_are_reported_and_not_counted_as_duplicate_ids(tmp_path):
    _write_dataset(
        tmp_path,
        [
            _event("", 2020, event_date="2020-01-01"),
            _event("", 2020, event_date="2020-01-02"),
            _event("PRESENT", 2020, event_date="2020-01-03"),
        ],
    )

    result = build_historical_analytics(tmp_path, as_of_date=date(2026, 10, 27))

    dataset = result["dataset_inventory"][0]
    assert dataset["missing_event_ids"] == 2
    assert dataset["duplicate_quality"]["duplicate_event_id_rows"] == 0
    assert result["summary"]["unique_event_ids"] == 1
    assert result["summary"]["data_quality"]["missing_event_id_rows"] == 2


def test_coordinate_quality_uses_all_rows_as_denominator_and_separates_missing_from_invalid(tmp_path):
    _write_dataset(
        tmp_path,
        [
            _event("VALID", 2020, event_date="2020-01-01", latitude="0", longitude="0"),
            _event("BOTH_MISSING", 2020, event_date="2020-01-02"),
            _event("PARTIAL", 2020, event_date="2020-01-03", latitude="10"),
            _event("OUT_OF_RANGE", 2020, event_date="2020-01-04", latitude="91", longitude="20"),
        ],
    )

    quality = build_historical_analytics(
        tmp_path,
        as_of_date=date(2026, 10, 27),
    )["dataset_inventory"][0]["geography"]

    assert quality["rows_with_both_valid_coordinates"] == 1
    assert quality["coordinate_coverage_percent"] == 25
    assert quality["missing_latitude"] == 1
    assert quality["missing_longitude"] == 2
    assert quality["rows_with_partial_coordinates"] == 1
    assert quality["invalid_coordinate_rows"] == 1


def test_analytics_validates_canonical_csv_hash_after_crlf_checkout(tmp_path):
    dataset_dir = _write_dataset(tmp_path, [_event("A", 2020, event_date="2020-01-02")])
    dataset_path = dataset_dir / "floods.csv"
    original = dataset_path.read_bytes()
    dataset_path.write_bytes(original.replace(b"\n", b"\r\n"))

    result = build_historical_analytics(tmp_path)

    assert result["summary"]["unique_event_ids"] == 1
    assert result["dataset_inventory"][0]["sha256"] == sha256_file(
        dataset_path,
        normalize_csv_line_endings=True,
    )


def test_analytics_reject_missing_required_columns_and_corrupt_manifest(tmp_path):
    _write_dataset(
        tmp_path,
        [{"event_id": "A", "disaster_type": "Flood"}],
        columns=["event_id", "disaster_type"],
    )
    missing_columns = build_historical_analytics(tmp_path)
    assert missing_columns["status"] == "ERROR"
    assert "missing required columns" in missing_columns["validation_errors"][0]["error"]

    manifest_path = tmp_path / "ml" / "datasets" / "historical_data" / "processed" / "floods.manifest.json"
    manifest_path.write_text("{not-json", encoding="utf-8")
    corrupt_manifest = build_historical_analytics(tmp_path)
    assert corrupt_manifest["status"] == "ERROR"
    assert "Cannot read dataset manifest" in corrupt_manifest["validation_errors"][0]["error"]


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


def test_country_rankings_are_api_shaped_and_ties_are_sorted_by_country_name(tmp_path):
    _write_dataset(
        tmp_path,
        [
            _event("A", 2020, country="Zed", event_date="2020-01-01"),
            _event("B", 2021, country="Able", event_date="2021-01-01"),
            _event("C", 2022, country="Able", event_date="2022-01-01"),
            _event("D", 2022, country="", event_date="2022-01-01"),
        ],
    )

    result = build_historical_analytics(tmp_path, as_of_date=date(2026, 10, 27))

    assert result["summary"]["events_by_country"] == [
        {"country": "Able", "count": 2},
        {"country": "Zed", "count": 1},
    ]
    assert result["summary"]["data_quality"]["missing_event_id_rows"] == 0
    assert result["dataset_inventory"][0]["unique_event_ids"] == 4
    assert "path" not in result["dataset_inventory"][0]


def test_future_and_reversed_event_dates_are_reported_and_excluded_from_year_counts(tmp_path):
    _write_dataset(
        tmp_path,
        [
            _event("FUTURE", 2026, event_date="2026-11-10", end_date="2026-11-11"),
            _event("REVERSED", 2026, event_date="2026-04-02", end_date="2026-03-02"),
            _event("VALID", 2026, event_date="2026-05-01", end_date="2026-05-02"),
        ],
    )

    result = build_historical_analytics(tmp_path, as_of_date=date(2026, 10, 27))

    dataset = result["dataset_inventory"][0]
    assert dataset["date_coverage"]["future_start_dates"] == 1
    assert dataset["date_coverage"]["end_before_start"] == 1
    assert result["summary"]["events_by_year"] == {"2026": 1}
    assert result["summary"]["year_aggregation"]["excluded_future_start_date"] == 1
    assert result["summary"]["year_aggregation"]["excluded_end_before_start"] == 1
    assert "start date(s) occur after the validation date." in dataset["warnings"][0]
    assert result["summary"]["unique_event_ids"] == 3


def test_impossible_calendar_date_is_reported_and_not_grouped_by_year(tmp_path):
    _write_dataset(
        tmp_path,
        [_event("IMPOSSIBLE", 2020, event_date="2020-02-30")],
    )

    result = build_historical_analytics(tmp_path, as_of_date=date(2026, 10, 27))

    assert result["dataset_inventory"][0]["date_coverage"]["invalid_start_dates"] == 1
    assert result["summary"]["events_by_year"] == {}
    assert result["summary"]["year_aggregation"]["excluded_invalid_start_date"] == 1
    assert result["summary"]["unique_event_ids"] == 1


def test_impact_coverage_distinguishes_reported_zero_missing_invalid_and_negative_values(tmp_path):
    _write_dataset(
        tmp_path,
        [
            _event("ZERO", 2020, event_date="2020-01-01", deaths="0"),
            _event("VALUE", 2020, event_date="2020-01-02", deaths="4"),
            _event("MISSING", 2020, event_date="2020-01-03", deaths=""),
            _event("INVALID", 2020, event_date="2020-01-04", deaths="bad"),
            _event("NEGATIVE", 2020, event_date="2020-01-05", deaths="-1"),
        ],
    )

    result = build_historical_analytics(tmp_path, as_of_date=date(2026, 10, 27))

    coverage = result["dataset_inventory"][0]["impact_coverage"]["total_deaths"]
    aggregate = result["summary"]["reported_impacts"]["total_deaths"]
    assert coverage["reported_records"] == 2
    assert coverage["explicit_zero_records"] == 1
    assert coverage["missing_records"] == 1
    assert coverage["invalid_records"] == 1
    assert coverage["negative_records"] == 1
    assert coverage["coverage_percent"] == 40
    assert coverage["unit"] == "people"
    assert aggregate["sum_of_reported_values"] == 4
    assert aggregate["reported_records"] == 2
    assert aggregate["explicit_zero_records"] == 1


def test_partial_results_keep_valid_datasets_and_report_failed_manifests(tmp_path):
    dataset_dir = _write_dataset(
        tmp_path,
        [_event("A", 2020, event_date="2020-01-01")],
    )
    (dataset_dir / "earthquakes.manifest.json").write_text("{broken", encoding="utf-8")

    result = build_historical_analytics(tmp_path, as_of_date=date(2026, 10, 27))

    assert result["status"] == "PARTIAL"
    assert result["summary"]["unique_event_ids"] == 1
    assert result["summary"]["source_rows_across_extracts"] == 1
    assert result["validation_errors"][0]["dataset"] == "earthquakes"
    assert {
        item["name"]: item["manifest_validation"]
        for item in result["dataset_inventory"]
    } == {"earthquakes": "ERROR", "floods": "VALIDATED"}


def test_empty_or_invalid_only_dataset_returns_explicit_error_status(tmp_path):
    _write_dataset(tmp_path, [])

    result = build_historical_analytics(tmp_path, as_of_date=date(2026, 10, 27))

    assert result["status"] == "ERROR"
    assert result["summary"]["source_rows_across_extracts"] == 0
    assert result["summary"]["unique_event_ids"] == 0
    assert result["validation_errors"][0]["dataset"] == "floods"
