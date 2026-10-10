import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.dummy import DummyRegressor

from ml.evaluation.model_evaluation import evaluate_model
from ml.models.disaster_prediction import build_disaster_prediction_model
from ml.preprocessing.data_cleaning import clean_dataframe
from ml.preprocessing.data_validation import validate_training_data
from ml.preprocessing.dataset_manifest import default_manifest_path, load_dataset_manifest
from ml.preprocessing.feature_engineering import (
    FLOOD_FEATURES,
    FLOOD_FEATURE_SCHEMA_VERSION,
    select_features,
)
from ml.training.hyperparameter_tuning import tune_model

DEFAULT_MODEL_PATH = Path(__file__).resolve().parents[1] / "models" / "trained_models" / "flood_risk_model.joblib"
TIME_COLUMNS = ("observation_time", "event_date", "start_date", "timestamp", "date", "start_year")


def _chronological_holdout(frame: pd.DataFrame, *, test_fraction: float = 0.2) -> tuple[np.ndarray, np.ndarray, str]:
    available_columns = [name for name in TIME_COLUMNS if name in frame.columns]
    if not available_columns:
        raise ValueError(
            "Training data must include an observation_time, event_date, start_date, timestamp, date, "
            "or start_year column so evaluation can use a chronological holdout."
        )

    time_column = ""
    timestamps: pd.Series | None = None
    for candidate in available_columns:
        if candidate == "start_year":
            years = pd.to_numeric(frame[candidate], errors="coerce")
            parsed = pd.to_datetime(years.astype("Int64").astype("string"), format="%Y", errors="coerce", utc=True)
        else:
            parsed = pd.to_datetime(frame[candidate], errors="coerce", utc=True)
        if parsed.notna().all():
            time_column = candidate
            timestamps = parsed
            break
    if timestamps is None:
        raise ValueError(
            "Training data has time columns, but none contains a valid time value for every labeled row."
        )

    unique_times = np.sort(timestamps.unique())
    if len(unique_times) < 3:
        raise ValueError("At least three distinct time periods are required for a chronological holdout.")
    split_at = max(2, min(len(unique_times) - 1, int(len(unique_times) * (1 - test_fraction))))
    first_test_time = unique_times[split_at]
    train_indices = np.flatnonzero(timestamps.to_numpy() < first_test_time)
    test_indices = np.flatnonzero(timestamps.to_numpy() >= first_test_time)
    if len(train_indices) < 2 or not len(test_indices):
        raise ValueError("The chronological split must contain at least two training rows and one test row.")
    return train_indices, test_indices, time_column


def train_from_csv(
    dataset_path: str | Path,
    *,
    target: str = "FloodProbability",
    output_path: str | Path = DEFAULT_MODEL_PATH,
    manifest_path: str | Path | None = None,
    tune: bool = False,
) -> dict:
    """Train using a provenance-checked dataset and chronological holdout."""
    dataset = Path(dataset_path)
    manifest_file = Path(manifest_path) if manifest_path else default_manifest_path(dataset)
    manifest = load_dataset_manifest(manifest_file)
    frame = clean_dataframe(pd.read_csv(dataset_path))
    if target not in frame.columns:
        raise ValueError(f"Training CSV must contain target column {target!r}.")
    try:
        frame[target] = pd.to_numeric(frame[target], errors="raise")
    except (TypeError, ValueError) as error:
        raise ValueError(f"Target column {target!r} must contain numeric values.") from error
    if frame[target].isna().any():
        raise ValueError(f"Target column {target!r} contains missing labels; resolve them explicitly.")
    validate_training_data(frame, target=target)
    if len(frame) < 5:
        raise ValueError("At least five labeled rows are required to train and evaluate the model.")

    features = select_features(frame, FLOOD_FEATURES)
    labels = frame[target].astype(float)
    if not labels.between(0, 1).all():
        raise ValueError(f"Target {target!r} must be a continuous index between 0 and 1.")
    train_indices, test_indices, time_column = _chronological_holdout(frame)
    train_features = features.iloc[train_indices]
    test_features = features.iloc[test_indices]
    train_labels = labels.iloc[train_indices]
    test_labels = labels.iloc[test_indices]

    if tune:
        search = tune_model(build_disaster_prediction_model(), train_features, train_labels)
        evaluated_model = search.best_estimator_
        parameters = search.best_params_
    else:
        evaluated_model = build_disaster_prediction_model()
        evaluated_model.fit(train_features, train_labels)
        parameters = evaluated_model.get_params(deep=True)

    metrics = evaluate_model(evaluated_model, test_features, test_labels)
    baseline_model = DummyRegressor(strategy="mean")
    baseline_model.fit(train_features, train_labels)
    baseline_metrics = evaluate_model(baseline_model, test_features, test_labels)
    final_model = build_disaster_prediction_model()
    if tune:
        final_model.set_params(**parameters)
    final_model.fit(features, labels)

    trained_at = datetime.now(timezone.utc)
    dataset_hash = hashlib.sha256(dataset.read_bytes()).hexdigest()
    manifest_hash = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    model_version = f"flood-risk-{trained_at.strftime('%Y%m%dT%H%M%SZ')}"
    artifact_path = Path(output_path)
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "model": final_model,
            "feature_names": list(FLOOD_FEATURES),
            "target": target,
            "metrics": metrics,
            "baseline_metrics": baseline_metrics,
            "training_rows": len(frame),
            "metadata": {
                "model_version": model_version,
                "training_data_version": dataset_hash,
                "dataset_manifest_version": manifest["dataset_version"],
                "dataset_manifest_sha256": manifest_hash,
                "dataset_manifest": manifest,
                "training_timestamp": trained_at.isoformat(),
                "feature_schema_version": FLOOD_FEATURE_SCHEMA_VERSION,
                "package_versions": {
                    "numpy": np.__version__,
                    "pandas": pd.__version__,
                    "scikit-learn": sklearn.__version__,
                    "joblib": joblib.__version__,
                },
                "feature_names": list(FLOOD_FEATURES),
                "model_type": type(final_model.named_steps["model"]).__name__,
                "training_rows": len(frame),
                "evaluation_method": "chronological_holdout",
                "time_column": time_column,
                "test_rows": len(test_indices),
                "metrics": metrics,
                "baseline_metrics": baseline_metrics,
                "target_definition": manifest["target_definition"],
                "target_interpretation": manifest["target_interpretation"],
            },
        },
        artifact_path,
    )
    return {
        "model_path": str(artifact_path),
        "training_rows": len(frame),
        "metrics": metrics,
        "baseline_metrics": baseline_metrics,
        "metadata": {
            "model_version": model_version,
            "training_data_version": dataset_hash,
            "dataset_manifest_version": manifest["dataset_version"],
            "dataset_manifest_sha256": manifest_hash,
            "training_timestamp": trained_at.isoformat(),
            "feature_schema_version": FLOOD_FEATURE_SCHEMA_VERSION,
            "training_rows": len(frame),
            "test_rows": len(test_indices),
            "metrics": metrics,
            "baseline_metrics": baseline_metrics,
            "target_definition": manifest["target_definition"],
            "target_interpretation": manifest["target_interpretation"],
            "evaluation_method": "chronological_holdout",
            "time_column": time_column,
            "test_rows": len(test_indices),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the DisasterGuard flood continuous-index regression model.")
    parser.add_argument("dataset", type=Path, help="CSV containing the 20 flood features and target")
    parser.add_argument("--target", default="FloodProbability", help="Numeric target column in [0, 1]")
    parser.add_argument("--output", type=Path, default=DEFAULT_MODEL_PATH, help="Output joblib model path")
    parser.add_argument(
        "--manifest",
        type=Path,
        help="Dataset provenance JSON (defaults to <dataset-stem>.manifest.json)",
    )
    parser.add_argument("--tune", action="store_true", help="Run cross-validated hyperparameter search")
    arguments = parser.parse_args()
    result = train_from_csv(
        arguments.dataset,
        target=arguments.target,
        output_path=arguments.output,
        manifest_path=arguments.manifest,
        tune=arguments.tune,
    )
    print(f"Saved model: {result['model_path']}")
    print(f"Holdout metrics: {result['metrics']}")


if __name__ == "__main__":
    main()
