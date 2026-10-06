import pandas as pd

from ml.preprocessing.historical_disasters.clean_emdat import build_cleaned_frame


def test_build_cleaned_frame_handles_missing_date_parts() -> None:
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
            "End Day": None,
            "Latitude": 19.076,
            "Longitude": 72.877,
            "Total Deaths": 12,
        }
    ])

    cleaned = build_cleaned_frame(frame)

    assert cleaned["start_date"].iloc[0] == pd.Timestamp("2020-01-01")
    assert cleaned["end_date"].iloc[0] == pd.Timestamp("2020-08-01")
    assert cleaned["event_date"].iloc[0] == pd.Timestamp("2020-01-01")
