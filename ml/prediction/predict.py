import argparse
from datetime import datetime
from functools import lru_cache
import hashlib
import importlib
import json
import logging
import os
from pathlib import Path
import re
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline

from ml.models.risk_classification import classify_risk
from ml.preprocessing.dataset_manifest import validate_dataset_manifest
from ml.preprocessing.feature_engineering import (
    FLOOD_FEATURES,
    FLOOD_FEATURE_SCHEMA_VERSION,
    select_features,
)

logger = logging.getLogger(__name__)
DEFAULT_MODEL_PATH = Path(
    os.getenv(
        "DISASTERGUARD_MODEL_PATH",
        str(Path(__file__).resolve().parents[1] / "models" / "trained_models" / "flood_risk_model.joblib"),
    )
)


def _validate_artifact(artifact: Any) -> dict[str, Any]:
    if not isinstance(artifact, dict):
        raise ValueError("Model artifact must be a dictionary.")
    model = artifact.get("model")
    if not isinstance(model, Pipeline) or set(model.named_steps) != {"preprocessor", "model"}:
        raise ValueError("Model artifact must contain the fitted preprocessor/model pipeline.")

    feature_names = artifact.get("feature_names")
    if feature_names != list(FLOOD_FEATURES):
        raise ValueError("Model artifact feature names/order do not match the canonical flood schema.")
    if list(getattr(model, "feature_names_in_", [])) != list(FLOOD_FEATURES):
        raise ValueError("Fitted model input features/order do not match the canonical flood schema.")
    if artifact.get("target") != "FloodProbability":
        raise ValueError("Model artifact target must be FloodProbability.")

    metadata = artifact.get("metadata")
    if not isinstance(metadata, dict):
        raise ValueError("Model artifact is missing training metadata.")
    if metadata.get("feature_schema_version") != FLOOD_FEATURE_SCHEMA_VERSION:
        raise ValueError("Model artifact feature schema version is missing or unsupported.")
    package_versions = metadata.get("package_versions")
    if not isinstance(package_versions, dict) or not all(
        isinstance(package_versions.get(name), str) and package_versions[name]
        for name in ("numpy", "pandas", "scikit-learn", "joblib")
    ):
        raise ValueError("Model artifact is missing the package versions used for training.")
    if metadata.get("feature_names") != list(FLOOD_FEATURES):
        raise ValueError("Training metadata feature names/order do not match the canonical schema.")
    if metadata.get("model_type") != type(model.named_steps["model"]).__name__:
        raise ValueError("Model artifact type does not match its training metadata.")
    if metadata.get("evaluation_method") != "chronological_holdout":
        raise ValueError("Model artifact has no documented chronological holdout evaluation.")
    if not isinstance(metadata.get("model_version"), str) or not metadata["model_version"].strip():
        raise ValueError("Model artifact is missing its model version.")
    if not isinstance(metadata.get("training_timestamp"), str) or not metadata["training_timestamp"].strip():
        raise ValueError("Model artifact is missing its training timestamp.")
    try:
        training_timestamp = datetime.fromisoformat(metadata["training_timestamp"])
    except ValueError as error:
        raise ValueError("Model artifact training timestamp is invalid.") from error
    if training_timestamp.tzinfo is None:
        raise ValueError("Model artifact training timestamp must include a timezone.")
    if not isinstance(metadata.get("training_rows"), int) or metadata["training_rows"] < 5:
        raise ValueError("Model artifact has insufficient documented training rows.")
    if artifact.get("training_rows") != metadata["training_rows"]:
        raise ValueError("Top-level and metadata training row counts do not match.")
    data_hash = metadata.get("training_data_version")
    if not isinstance(data_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", data_hash):
        raise ValueError("Model artifact is missing its training dataset SHA-256.")
    manifest = validate_dataset_manifest(metadata.get("dataset_manifest"))
    if metadata.get("target_definition") != manifest["target_definition"]:
        raise ValueError("Model artifact target definition does not match its provenance manifest.")
    if manifest["target_interpretation"] != "continuous_index":
        raise ValueError("Model artifact target is not a supported continuous index.")
    expected_manifest_hash = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if metadata.get("dataset_manifest_sha256") != expected_manifest_hash:
        raise ValueError("Model artifact dataset manifest hash does not match its provenance metadata.")
    metrics = metadata.get("metrics")
    baseline_metrics = metadata.get("baseline_metrics")
    if (
        not isinstance(metrics, dict)
        or not all(key in metrics and isinstance(metrics[key], (int, float)) and np.isfinite(metrics[key]) for key in ("mae", "rmse"))
    ):
        raise ValueError("Model artifact is missing finite holdout MAE/RMSE metrics.")
    if (
        not isinstance(baseline_metrics, dict)
        or not all(
            key in baseline_metrics
            and isinstance(baseline_metrics[key], (int, float))
            and np.isfinite(baseline_metrics[key])
            for key in ("mae", "rmse")
        )
    ):
        raise ValueError("Model artifact is missing finite baseline holdout metrics.")
    if not isinstance(metadata.get("test_rows"), int) or metadata["test_rows"] < 1:
        raise ValueError("Model artifact has no held-out test rows.")
    if artifact.get("metrics") != metrics:
        raise ValueError("Top-level and metadata holdout metrics do not match.")
    if artifact.get("baseline_metrics") != baseline_metrics:
        raise ValueError("Top-level and metadata baseline metrics do not match.")

    probe = pd.DataFrame([{name: 8.0 for name in FLOOD_FEATURES}], columns=FLOOD_FEATURES)
    output = np.asarray(model.predict(probe), dtype=float)
    if output.shape != (1,) or not np.isfinite(output).all() or not 0 <= output[0] <= 1:
        raise ValueError("Model artifact failed a finite, in-range one-row inference check.")
    return artifact


@lru_cache(maxsize=8)
def _load_model_artifact_cached(path: str, modified_ns: int, size: int) -> dict[str, Any]:
    _ = modified_ns, size
    return _validate_artifact(joblib.load(path))


def load_model_artifact(model_path: str | Path = DEFAULT_MODEL_PATH) -> dict[str, Any]:
    """Load and validate a model once per unchanged artifact file."""
    path = Path(model_path).expanduser().resolve()
    stat = path.stat()
    return _load_model_artifact_cached(str(path), stat.st_mtime_ns, stat.st_size)


def get_model_readiness(model_path: str | Path = DEFAULT_MODEL_PATH) -> dict[str, Any]:
    path = Path(model_path).expanduser()
    if not path.is_file():
        return {
            "status": "NOT_READY",
            "message": f"No trained model artifact exists at {path}.",
            "model_version": None,
            "metrics": None,
        }
    try:
        artifact = load_model_artifact(path)
    except Exception as error:
        logger.warning("Configured flood model artifact is invalid (%s).", type(error).__name__)
        return {
            "status": "NOT_READY",
            "message": f"The configured model artifact failed validation: {error}",
            "model_version": None,
            "metrics": None,
        }
    metadata = artifact["metadata"]
    return {
        "status": "READY",
        "message": (
            "The model artifact, declared provenance, schema, holdout metrics, and inference probe pass "
            "structural checks. Source data quality is not independently authenticated by the backend."
        ),
        "model_version": metadata["model_version"],
        "metrics": metadata["metrics"],
        "baseline_metrics": metadata["baseline_metrics"],
        "feature_schema_verified": True,
    }


def _contributions(
    artifact: dict[str, Any],
    features: pd.DataFrame,
) -> list[dict[str, float | str]]:
    project_root = str(Path(__file__).resolve().parents[2])
    if project_root not in os.sys.path:
        os.sys.path.insert(0, project_root)
    try:
        shap_analysis = importlib.import_module("explainable-ai.shap_analysis")
        feature_importance = importlib.import_module("explainable-ai.feature_importance")
        _, contributions = shap_analysis.calculate_shap_values(artifact, features)
        return feature_importance.rank_feature_importance(contributions, limit=5)
    except Exception as error:
        logger.warning("SHAP explanation unavailable (%s).", type(error).__name__)
        return []


def predict_risk(
    inputs: dict[str, Any],
    model_path: str | Path = DEFAULT_MODEL_PATH,
) -> dict[str, Any]:
    """Run the validated continuous-index model; never impute or clip bad inference data."""
    if set(inputs) != set(FLOOD_FEATURES):
        missing = [name for name in FLOOD_FEATURES if name not in inputs]
        extra = sorted(set(inputs) - set(FLOOD_FEATURES))
        details = []
        if missing:
            details.append(f"missing features: {', '.join(missing)}")
        if extra:
            details.append(f"unexpected features: {', '.join(extra)}")
        raise ValueError("Prediction input does not match the canonical schema (" + "; ".join(details) + ").")
    artifact = load_model_artifact(model_path)
    features = select_features(pd.DataFrame([inputs]))
    output = np.asarray(artifact["model"].predict(features), dtype=float)
    if output.shape != (1,) or not np.isfinite(output).all() or not 0 <= output[0] <= 1:
        raise ValueError("Model returned a non-finite or out-of-range continuous target.")
    target_value = float(output[0])
    score, band = classify_risk(target_value)
    contributions = _contributions(artifact, features)
    metadata = artifact["metadata"]
    interpretation = metadata["target_interpretation"]
    explanation = (
        f"The model's continuous FloodProbability target estimate is {target_value:.4f}. "
        "It is not a calibrated event probability or an official forecast."
    )
    if contributions:
        explanation += (
            f" The largest SHAP contribution is {contributions[0]['feature']}; "
            "SHAP describes model contribution, not causation."
        )
    else:
        explanation += " A validated SHAP explanation is unavailable for this model/environment."

    return {
        "offline": False,
        "target_value": target_value,
        "target_interpretation": interpretation,
        "risk_score": score,
        "risk_band": band,
        "model_version": metadata["model_version"],
        "explanation": explanation,
        "top_contributions": contributions,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Predict the documented continuous flood-risk index from JSON features.")
    parser.add_argument("input", type=Path, help="JSON file containing the canonical 20 flood features")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH, help="Validated joblib model")
    arguments = parser.parse_args()
    with arguments.input.open(encoding="utf-8") as input_file:
        inputs = json.load(input_file)
    print(json.dumps(predict_risk(inputs, arguments.model), indent=2))


if __name__ == "__main__":
    main()
