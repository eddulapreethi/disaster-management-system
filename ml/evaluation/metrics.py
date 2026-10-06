import numpy as np
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score


def regression_metrics(actual, predicted) -> dict[str, float | None]:
    """Calculate standard regression metrics for probability predictions."""
    actual_values = np.asarray(actual, dtype=float)
    predicted_values = np.asarray(predicted, dtype=float)
    if actual_values.size == 0 or actual_values.shape != predicted_values.shape:
        raise ValueError("Actual and predicted values must have the same non-empty shape.")
    return {
        "mae": float(mean_absolute_error(actual_values, predicted_values)),
        "rmse": float(np.sqrt(mean_squared_error(actual_values, predicted_values))),
        "r2": float(r2_score(actual_values, predicted_values)) if actual_values.size >= 2 else None,
    }
