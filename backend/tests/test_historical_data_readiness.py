import hashlib
import json

from app.services.historical_data_readiness import get_historical_analytics, get_historical_data_readiness


def test_historical_data_manifest_validation_never_marks_events_trainable(tmp_path) -> None:
    project = tmp_path
    source_dir = project / "ml" / "datasets" / "historical_disasters" / "EM-DAT"
    processed_dir = project / "ml" / "datasets" / "historical_data" / "processed"
    source_dir.mkdir(parents=True)
    processed_dir.mkdir(parents=True)
    (source_dir / "emdat.xlsx").write_bytes(b"source workbook fixture")
    dataset = processed_dir / "floods.csv"
    dataset.write_text("event_id,disaster_type\n1,Flood\n", encoding="utf-8")
    digest = hashlib.sha256(dataset.read_bytes()).hexdigest()
    manifest = {
        "dataset_name": "floods",
        "row_count": 1,
        "dataset_sha256": digest,
        "validation": {"sha256": digest, "non_empty": True},
    }
    (processed_dir / "floods.manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )

    result = get_historical_data_readiness(project)

    assert result["source_status"] == "VALIDATED"
    assert result["status"] == "NOT_READY"
    assert result["analytics_status"] == "ERROR"
    assert result["training_status"] == "NOT_READY"
    assert result["validated_event_datasets"][0]["status"] == "VALIDATED"
    assert result["training_blockers"]


def test_missing_workbook_reports_unavailable_source(tmp_path) -> None:
    result = get_historical_data_readiness(tmp_path)

    assert result["status"] == "NOT_READY"
    assert result["analytics_status"] == "UNAVAILABLE"
    assert result["source_status"] == "UNAVAILABLE"


def test_hash_mismatch_is_reported_as_validation_error(tmp_path) -> None:
    source_dir = tmp_path / "ml" / "datasets" / "historical_disasters" / "EM-DAT"
    processed_dir = tmp_path / "ml" / "datasets" / "historical_data" / "processed"
    source_dir.mkdir(parents=True)
    processed_dir.mkdir(parents=True)
    (source_dir / "emdat.xlsx").write_bytes(b"source workbook fixture")
    dataset = processed_dir / "floods.csv"
    dataset.write_text("event_id\n1\n", encoding="utf-8")
    (processed_dir / "floods.manifest.json").write_text(
        json.dumps(
            {
                "dataset_name": "floods",
                "row_count": 1,
                "dataset_sha256": "incorrect",
                "validation": {"sha256": "incorrect", "non_empty": True},
            }
        ),
        encoding="utf-8",
    )

    result = get_historical_data_readiness(tmp_path)

    assert result["source_status"] == "UNVALIDATED"
    assert result["validated_event_datasets"][0]["status"] == "ERROR"


def test_valid_historical_events_are_ready_for_analytics_not_supervised_training(tmp_path) -> None:
    source_dir = tmp_path / "ml" / "datasets" / "historical_disasters" / "EM-DAT"
    processed_dir = tmp_path / "ml" / "datasets" / "historical_data" / "processed"
    source_dir.mkdir(parents=True)
    processed_dir.mkdir(parents=True)
    source = source_dir / "source.xlsx"
    source.write_bytes(b"test source workbook")
    processed_input = processed_dir / "emdat_cleaned.csv"
    processed_input.write_text("test input\n", encoding="utf-8")
    dataset = processed_dir / "floods.csv"
    dataset.write_text(
        "disno.,disaster_type,country,start_year,start_date,latitude,longitude,total_deaths,total_affected,total_damage_'000_us$\n"
        "2020-0001,Flood,Testland,2020,2020-01-01,10,20,1,4,5\n",
        encoding="utf-8",
    )
    digest = hashlib.sha256(dataset.read_bytes()).hexdigest()
    manifest = {
        "dataset_name": "floods",
        "row_count": 1,
        "dataset_sha256": digest,
        "source_file": source.name,
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "processed_input_file": processed_input.name,
        "processed_input_sha256": hashlib.sha256(processed_input.read_bytes()).hexdigest(),
        "event_categories": ["Flood"],
        "target_definition": "Historical event classification only.",
        "validation": {"sha256": digest, "non_empty": True},
    }
    (processed_dir / "floods.manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    result = get_historical_data_readiness(tmp_path)

    assert result["status"] == "READY"
    assert result["analytics_status"] == "READY"
    assert result["training_status"] == "NOT_READY"
    assert result["analytics_summary"]["unique_event_ids"] == 1
    assert "supervised flood training remains blocked" in result["message"]


def test_historical_analytics_cache_is_invalidated_when_dataset_changes(tmp_path) -> None:
    source_dir = tmp_path / "ml" / "datasets" / "historical_disasters" / "EM-DAT"
    processed_dir = tmp_path / "ml" / "datasets" / "historical_data" / "processed"
    source_dir.mkdir(parents=True)
    processed_dir.mkdir(parents=True)
    source = source_dir / "source.xlsx"
    source.write_bytes(b"test source workbook")
    processed_input = processed_dir / "emdat_cleaned.csv"
    processed_input.write_text("test input\n", encoding="utf-8")
    dataset = processed_dir / "floods.csv"
    dataset.write_text(
        "disno.,disaster_type,country,start_year,start_date,latitude,longitude,total_deaths,total_affected,total_damage_'000_us$\n"
        "2020-0001,Flood,Testland,2020,2020-01-01,10,20,1,4,5\n",
        encoding="utf-8",
    )
    digest = hashlib.sha256(dataset.read_bytes()).hexdigest()
    manifest = {
        "dataset_name": "floods",
        "row_count": 1,
        "dataset_sha256": digest,
        "source_file": source.name,
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "processed_input_file": processed_input.name,
        "processed_input_sha256": hashlib.sha256(processed_input.read_bytes()).hexdigest(),
        "event_categories": ["Flood"],
        "target_definition": "Historical event classification only.",
        "validation": {"sha256": digest, "non_empty": True},
    }
    (processed_dir / "floods.manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    first = get_historical_analytics(tmp_path)
    assert first["summary"]["unique_event_ids"] == 1

    extra_rows = (
        "2020-0001,Flood,Testland,2020,2020-01-01,10,20,1,4,5\n"
        "2020-0002,Flood,Testland,2020,2020-01-02,15,25,2,3,6\n"
    )
    dataset.write_text(
        "disno.,disaster_type,country,start_year,start_date,latitude,longitude,total_deaths,total_affected,total_damage_'000_us$\n"
        + extra_rows,
        encoding="utf-8",
    )
    manifest["row_count"] = 2
    manifest["dataset_sha256"] = hashlib.sha256(dataset.read_bytes()).hexdigest()
    manifest["validation"]["sha256"] = manifest["dataset_sha256"]
    (processed_dir / "floods.manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    second = get_historical_analytics(tmp_path)
    assert second["summary"]["unique_event_ids"] == 2
    assert second["summary"]["events_by_disaster_type"]["Flood"] == 2
