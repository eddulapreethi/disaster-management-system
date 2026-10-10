import joblib
import json
from pathlib import Path
import pandas as pd
import pytest

from ml.preprocessing.dataset_manifest import default_manifest_path
from ml.preprocessing.feature_engineering import FLOOD_FEATURES
from ml.prediction.predict import get_model_readiness, predict_risk
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


def _write_manifest(dataset: Path) -> None:
    manifest = {
        "dataset_name": "test-fixture-only",
        "dataset_version": "test-v1",
        "source_name": "synthetic unit-test fixture",
        "source_reference": "unit test",
        "license": "not applicable to test fixture",
        "geographic_coverage": "synthetic",
        "temporal_coverage": "2020-2024 synthetic",
        "spatiotemporal_linkage": "synthetic test rows; not operational data",
        "row_definition": "one generated fixture row per synthetic year",
        "grouping_policy": "unit-test-only synthetic rows",
        "target_definition": "synthetic continuous target used only to test training code",
        "target_interpretation": "continuous_index",
        "feature_schema_version": "flood-risk-factors-v1",
        "feature_definitions": {
            name: {
                "meaning": f"synthetic test fixture for {name}",
                "data_type": "numeric",
                "unit": "synthetic 0-16 index",
                "minimum": 0,
                "maximum": 16,
                "source": "generated in the unit test; not a real data source",
                "transformation": "none",
            }
            for name in FLOOD_FEATURES
        },
    }
    default_manifest_path(dataset).write_text(json.dumps(manifest), encoding="utf-8")


def test_training_requires_time_column_for_leakage_safe_evaluation(tmp_path) -> None:
    dataset = tmp_path / "training.csv"
    frame = _training_frame().drop(columns=["start_year"])
    frame.to_csv(dataset, index=False)
    _write_manifest(dataset)

    with pytest.raises(ValueError, match="chronological holdout"):
        train_from_csv(dataset, output_path=tmp_path / "model.joblib")


def test_training_saves_feature_schema_and_chronological_evaluation_metadata(tmp_path) -> None:
    dataset = tmp_path / "training.csv"
    artifact_path = tmp_path / "model.joblib"
    _training_frame().to_csv(dataset, index=False)
    _write_manifest(dataset)

    result = train_from_csv(dataset, output_path=artifact_path)

    artifact = joblib.load(artifact_path)
    assert result["metadata"]["evaluation_method"] == "chronological_holdout"
    assert result["metadata"]["time_column"] == "start_year"
    assert artifact["metadata"]["feature_names"] == list(FLOOD_FEATURES)
    assert artifact["metadata"]["training_data_version"] == result["metadata"]["training_data_version"]
    assert artifact["metadata"]["feature_schema_version"] == "flood-risk-factors-v1"
    assert artifact["metadata"]["target_interpretation"] == "continuous_index"
    readiness = get_model_readiness(artifact_path)
    assert readiness["status"] == "READY"
    prediction = predict_risk({name: 2.0 for name in FLOOD_FEATURES}, artifact_path)
    assert 0 <= prediction["target_value"] <= 1
    assert prediction["target_interpretation"] == "continuous_index"
    assert prediction["model_version"] == result["metadata"]["model_version"]


def test_training_requires_a_complete_dataset_provenance_manifest(tmp_path) -> None:
    dataset = tmp_path / "training.csv"
    _training_frame().to_csv(dataset, index=False)

    with pytest.raises(ValueError, match="requires a provenance manifest"):
        train_from_csv(dataset, output_path=tmp_path / "model.joblib")


def test_missing_model_artifact_is_not_ready(tmp_path) -> None:
    readiness = get_model_readiness(tmp_path / "not-installed.joblib")

    assert readiness["status"] == "NOT_READY"
    assert "No trained model artifact" in readiness["message"]


def test_training_rejects_missing_targets_instead_of_dropping_rows(tmp_path) -> None:
    dataset = tmp_path / "training.csv"
    frame = _training_frame()
    frame.loc[0, "FloodProbability"] = float("nan")
    frame.to_csv(dataset, index=False)
    _write_manifest(dataset)

    with pytest.raises(ValueError, match="contains missing labels"):
        train_from_csv(dataset, output_path=tmp_path / "model.joblib")


def test_training_rejects_manifest_range_that_conflicts_with_canonical_schema(tmp_path) -> None:
    dataset = tmp_path / "training.csv"
    _training_frame().to_csv(dataset, index=False)
    _write_manifest(dataset)
    manifest_path = default_manifest_path(dataset)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["feature_definitions"]["MonsoonIntensity"]["maximum"] = 100
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="canonical numeric range"):
        train_from_csv(dataset, output_path=tmp_path / "model.joblib")
