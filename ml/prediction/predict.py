import argparse
import importlib
import json
import os
from pathlib import Path
import sys
from typing import Any

import joblib
import numpy as np
import pandas as pd

from ml.models.risk_classification import classify_risk
from ml.preprocessing.feature_engineering import FLOOD_FEATURES, select_features

DEFAULT_MODEL_PATH = Path(
    os.getenv(
        "DISASTERGUARD_MODEL_PATH",
        str(Path(__file__).resolve().parents[1] / "models" / "trained_models" / "flood_risk_model.joblib"),
    )
)


def predict_risk(
    inputs: dict[str, Any],
    model_path: str | Path = DEFAULT_MODEL_PATH,
) -> dict[str, Any]:
    """Predict flood probability and return local TreeSHAP contributions."""
    artifact_path = Path(model_path)
    if not artifact_path.is_file():
        raise FileNotFoundError(
            f"Trained model not found at {artifact_path}. Train it first with ml.training.train_model."
        )
    artifact = joblib.load(artifact_path)
    required_features = artifact.get("feature_names", list(FLOOD_FEATURES))
    missing = [name for name in required_features if name not in inputs]
    if missing:
        raise ValueError(f"Prediction input is missing features: {', '.join(missing)}")

    row = pd.DataFrame([{name: inputs[name] for name in required_features}])
    for name in required_features:
        row[name] = pd.to_numeric(row[name], errors="raise")
    values = row.loc[:, required_features].to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("Prediction features must be finite numbers.")
    if ((values < 0) | (values > 16)).any():
        raise ValueError("Flood risk features must be between 0 and 16.")

    model = artifact["model"]
    pipeline_features = select_features(row, required_features)
    probability = float(np.clip(model.predict(pipeline_features)[0], 0.0, 1.0))
    score, band = classify_risk(probability)

    project_root = str(Path(__file__).resolve().parents[2])
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    shap_analysis = importlib.import_module("explainable-ai.shap_analysis")
    feature_importance = importlib.import_module("explainable-ai.feature_importance")
    _expected_value, contributions = shap_analysis.calculate_shap_values(artifact, pipeline_features)
    top_contributions = feature_importance.rank_feature_importance(contributions, limit=5)
    main_driver = top_contributions[0]["feature"] if top_contributions else "the supplied conditions"

    return {
        "offline": False,
        "flood_probability": probability,
        "risk_score": score,
        "risk_band": band,
        "explanation": f"Estimated flood probability is {probability:.1%}; the strongest SHAP factor is {main_driver}.",
        "top_contributions": top_contributions,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Predict flood risk from a JSON feature object.")
    parser.add_argument("input", type=Path, help="JSON file containing the 20 flood features")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH, help="Trained joblib model")
    arguments = parser.parse_args()
    with arguments.input.open(encoding="utf-8") as input_file:
        inputs = json.load(input_file)
    print(json.dumps(predict_risk(inputs, arguments.model), indent=2))


if __name__ == "__main__":
    main()
