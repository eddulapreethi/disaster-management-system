import joblib
import pandas as pd
import pytest

from ml.preprocessing.feature_engineering import FLOOD_FEATURES
from ml.training.train_model import train_from_csv


def _training_frame() -> pd.DataFrame:
    return pd.DataFrame([
        {
            **{name: float(year - 2019) for name in FLOOD_FEATURES},
            "FloodProbability": 0.1 * (year - 2019),
            "start_year": year,
        }
        for year in range(2020, 2025)
    ])


def test_training_requires_time_column_for_leakage_safe_evaluation(tmp_path) -> None:
    dataset = tmp_path / "training.csv"
    frame = _training_frame().drop(columns=["start_year"])
    frame.to_csv(dataset, index=False)

    with pytest.raises(ValueError, match="chronological holdout"):
        train_from_csv(dataset, output_path=tmp_path / "model.joblib")


def test_training_saves_feature_schema_and_chronological_evaluation_metadata(tmp_path) -> None:
    dataset = tmp_path / "training.csv"
    artifact_path = tmp_path / "model.joblib"
    _training_frame().to_csv(dataset, index=False)

    result = train_from_csv(dataset, output_path=artifact_path)

    artifact = joblib.load(artifact_path)
    assert result["metadata"]["evaluation_method"] == "chronological_holdout"
    assert result["metadata"]["time_column"] == "start_year"
    assert artifact["metadata"]["feature_names"] == list(FLOOD_FEATURES)
    assert artifact["metadata"]["training_data_version"] == result["metadata"]["training_data_version"]
