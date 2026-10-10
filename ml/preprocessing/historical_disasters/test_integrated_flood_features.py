import pandas as pd
import pytest

from ml.preprocessing.flood_feature_integration import (
    build_integrated_historical_flood_features,
    integrate_historical_flood_dataset,
)


def test_emdat_event_records_do_not_generate_proxy_training_features() -> None:
    frame = pd.DataFrame([
        {
            "DisNo.": "EM-001",
            "Disaster Type": "Flood",
            "Disaster Subtype": "Flash flood",
            "Country": "India",
            "Subregion": "South Asia",
            "Location": "Bengaluru",
            "Start Year": 2021,
            "Latitude": 12.9716,
            "Longitude": 77.5946,
            "Total Deaths": 10,
            "No. Affected": 2500,
            "Total Affected": 2500,
            "Total Damage ('000 US$)": 1500,
            "River Basin": "Cauvery",
        }
    ])

    with pytest.raises(ValueError, match="NOT READY"):
        build_integrated_historical_flood_features(frame)

def test_emdat_dataset_does_not_write_a_training_matrix_when_not_ready(tmp_path) -> None:
    source = tmp_path / "emdat_flood_events.csv"
    output = tmp_path / "flood_feature_matrix.csv"
    pd.DataFrame([{"Disaster Type": "Flood", "Total Deaths": 4}]).to_csv(source, index=False)

    with pytest.raises(ValueError, match="NOT READY"):
        integrate_historical_flood_dataset(source, output)

    assert not output.exists()


def test_validates_and_preserves_real_feature_and_label_columns() -> None:
    from ml.preprocessing.feature_engineering import FLOOD_FEATURES

    frame = pd.DataFrame([{**{name: 1.25 for name in FLOOD_FEATURES}, "FloodProbability": 0.4}])

    integrated = build_integrated_historical_flood_features(frame)

    assert integrated.columns.tolist() == [*FLOOD_FEATURES, "FloodProbability"]
    assert integrated["FloodProbability"].between(0, 1).all()
    assert integrated.shape[0] == 1
    assert integrated.loc[0, "MonsoonIntensity"] == 1.25
