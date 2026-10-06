import argparse
from pathlib import Path

import joblib
import pandas as pd
from sklearn.model_selection import train_test_split

from ml.evaluation.model_evaluation import evaluate_model
from ml.models.disaster_prediction import build_disaster_prediction_model
from ml.preprocessing.data_cleaning import clean_dataframe
from ml.preprocessing.data_validation import validate_training_data
from ml.preprocessing.feature_engineering import FLOOD_FEATURES, select_features
from ml.training.hyperparameter_tuning import tune_model

DEFAULT_MODEL_PATH = Path(__file__).resolve().parents[1] / "models" / "trained_models" / "flood_risk_model.joblib"


def train_from_csv(
    dataset_path: str | Path,
    *,
    target: str = "FloodProbability",
    output_path: str | Path = DEFAULT_MODEL_PATH,
    tune: bool = False,
) -> dict:
    """Train, evaluate on a holdout set, then save a deployable model artifact."""
    frame = clean_dataframe(pd.read_csv(dataset_path))
    if target not in frame.columns:
        raise ValueError(f"Training CSV must contain target column {target!r}.")
    frame[target] = pd.to_numeric(frame[target], errors="coerce")
    frame = frame.dropna(subset=[target]).reset_index(drop=True)
    validate_training_data(frame, target=target)
    if len(frame) < 5:
        raise ValueError("At least five labeled rows are required to train and evaluate the model.")

    features = select_features(frame, FLOOD_FEATURES)
    labels = frame[target].astype(float)
    if not labels.between(0, 1).all():
        raise ValueError(f"Target {target!r} must contain probabilities between 0 and 1.")
    train_features, test_features, train_labels, test_labels = train_test_split(
        features,
        labels,
        test_size=0.2,
        random_state=42,
    )

    if tune:
        search = tune_model(build_disaster_prediction_model(), train_features, train_labels)
        evaluated_model = search.best_estimator_
        parameters = search.best_params_
    else:
        evaluated_model = build_disaster_prediction_model()
        evaluated_model.fit(train_features, train_labels)
        parameters = evaluated_model.get_params(deep=True)

    metrics = evaluate_model(evaluated_model, test_features, test_labels)
    final_model = build_disaster_prediction_model()
    if tune:
        final_model.set_params(**parameters)
    final_model.fit(features, labels)

    artifact_path = Path(output_path)
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "model": final_model,
            "feature_names": list(FLOOD_FEATURES),
            "target": target,
            "metrics": metrics,
            "training_rows": len(frame),
        },
        artifact_path,
    )
    return {"model_path": str(artifact_path), "training_rows": len(frame), "metrics": metrics}


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the DisasterGuard flood probability model.")
    parser.add_argument("dataset", type=Path, help="CSV containing the 20 flood features and target")
    parser.add_argument("--target", default="FloodProbability", help="Numeric target column in [0, 1]")
    parser.add_argument("--output", type=Path, default=DEFAULT_MODEL_PATH, help="Output joblib model path")
    parser.add_argument("--tune", action="store_true", help="Run cross-validated hyperparameter search")
    arguments = parser.parse_args()
    result = train_from_csv(
        arguments.dataset,
        target=arguments.target,
        output_path=arguments.output,
        tune=arguments.tune,
    )
    print(f"Saved model: {result['model_path']}")
    print(f"Holdout metrics: {result['metrics']}")


if __name__ == "__main__":
    main()
