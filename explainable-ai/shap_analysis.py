from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd
import shap


def calculate_shap_values(
    model_artifact: dict[str, Any],
    features: pd.DataFrame,
) -> tuple[float, list[dict[str, float | str]]]:
    """Return the model's expected value and per-feature TreeSHAP contributions.

    The artifact must contain the fitted sklearn pipeline saved by
    `ml.training.train_model`; `features` must contain one row in artifact order.
    Contributions are in the model output's units (flood probability, 0..1).
    """
    if len(features) != 1:
        raise ValueError("SHAP prediction explanations require exactly one feature row.")

    feature_names: Sequence[str] = model_artifact.get("feature_names", list(features.columns))
    missing = [name for name in feature_names if name not in features.columns]
    if missing:
        raise ValueError(f"Feature data is missing required columns: {', '.join(missing)}")

    ordered_features = features.loc[:, list(feature_names)]
    pipeline = model_artifact.get("model")
    if pipeline is None or "preprocessor" not in pipeline.named_steps or "model" not in pipeline.named_steps:
        raise ValueError("Model artifact must contain a fitted pipeline with preprocessor and model steps.")

    transformed = pipeline.named_steps["preprocessor"].transform(ordered_features)
    estimator = pipeline.named_steps["model"]
    explainer = shap.TreeExplainer(estimator)
    explanation = explainer(transformed)
    values = np.asarray(explanation.values).reshape(-1)
    expected_values = np.asarray(explanation.base_values).reshape(-1)
    if len(values) != len(feature_names):
        raise ValueError("SHAP returned a feature count that does not match the model artifact.")

    contributions = [
        {"feature": name, "shap_contribution": float(value)}
        for name, value in zip(feature_names, values, strict=True)
    ]
    contributions.sort(key=lambda contribution: abs(float(contribution["shap_contribution"])), reverse=True)
    expected_value = float(expected_values[0]) if expected_values.size else 0.0
    return expected_value, contributions
