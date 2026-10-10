import pandas as pd

from ml.preprocessing.historical_disasters.clean_emdat import build_cleaned_frame


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
