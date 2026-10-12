import pandas as pd
import json
import re

from ml.preprocessing.historical_disasters.clean_emdat import build_cleaned_frame
from ml.preprocessing.historical_disasters.filter_disasters import generate_disaster_specific_datasets


def test_build_cleaned_frame_preserves_unknown_date_parts_as_missing() -> None:
    frame = pd.DataFrame([
        {
            "DisNo.": "EM-001",
            "Disaster Type": "Flood",
            "Disaster Subtype": "Flash flood",
            "Country": "India",
            "Start Year": 2020,
            "Start Month": None,
            "Start Day": None,
            "End Year": 2020,
            "End Month": 8,
            "End Day": 14,
            "Latitude": 19.076,
            "Longitude": 72.877,
            "Total Deaths": 12,
        }
    ])

    cleaned = build_cleaned_frame(frame)

    assert pd.isna(cleaned["start_date"].iloc[0])
    assert cleaned["end_date"].iloc[0] == pd.Timestamp("2020-08-14")
    assert pd.isna(cleaned["event_date"].iloc[0])


def test_build_cleaned_frame_parses_complete_event_dates() -> None:
    frame = pd.DataFrame([
        {
            "DisNo.": "EM-002",
            "Disaster Type": "Flood",
            "Disaster Subtype": "Riverine flood",
            "Country": "India",
            "Start Year": 2020,
            "Start Month": 8,
            "Start Day": 12,
            "End Year": 2020,
            "End Month": 8,
            "End Day": 14,
            "Latitude": 19.076,
            "Longitude": 72.877,
        }
    ])

    cleaned = build_cleaned_frame(frame)

    assert cleaned["start_date"].iloc[0] == pd.Timestamp("2020-08-12")
    assert cleaned["end_date"].iloc[0] == pd.Timestamp("2020-08-14")


def test_event_filter_writes_manifest_and_keeps_glacial_floods_separate(tmp_path) -> None:
    source = tmp_path / "events.csv"
    output = tmp_path / "processed"
    pd.DataFrame([
        {
            "disno.": "EM-001",
            "disaster_type": "Flood",
            "country": "India",
            "start_year": 2020,
            "start_date": "2020-08-12",
            "latitude": 19.0,
            "longitude": 72.0,
        },
        {
            "disno.": "EM-002",
            "disaster_type": "Glacial lake outburst flood",
            "country": "Nepal",
            "start_year": 2021,
            "start_date": "2021-06-01",
            "latitude": None,
            "longitude": None,
        },
    ]).to_csv(source, index=False)

    results = generate_disaster_specific_datasets(source, output)
    flood_manifest = json.loads((output / "floods.manifest.json").read_text(encoding="utf-8"))
    glacial_manifest = json.loads(
        (output / "glacial_lake_outburst_floods.manifest.json").read_text(encoding="utf-8")
    )

    assert len(results["floods.csv"]) == 1
    assert len(results["glacial_lake_outburst_floods.csv"]) == 1
    assert flood_manifest["row_count"] == 1
    assert flood_manifest["validation"]["training_suitable"] is False
    assert flood_manifest["dataset_sha256"]
    assert flood_manifest["retrieval_date"] is None
    assert flood_manifest["source_filename_date"] is None or re.fullmatch(
        r"20\d{2}-\d{2}-\d{2}", flood_manifest["source_filename_date"]
    )
    assert flood_manifest["manifest_generated_at_utc"].endswith("Z")
    assert glacial_manifest["event_categories"] == ["Glacial lake outburst flood"]
