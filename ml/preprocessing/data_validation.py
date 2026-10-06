from collections.abc import Sequence

import numpy as np
import pandas as pd

from ml.preprocessing.feature_engineering import FLOOD_FEATURES


def validate_training_data(
    frame: pd.DataFrame,
    target: str = "FloodProbability",
    feature_names: Sequence[str] = FLOOD_FEATURES,
) -> None:
    """Validate the expected flood dataset columns and target values."""
    if frame.empty:
        raise ValueError("Training dataset is empty.")
    required = [*feature_names, target]
    missing = [name for name in required if name not in frame.columns]
    if missing:
        raise ValueError(f"Dataset is missing required columns: {', '.join(missing)}")
    for name in feature_names:
        try:
            values = pd.to_numeric(frame[name], errors="raise")
        except (TypeError, ValueError) as error:
            raise ValueError(f"Feature column {name!r} must contain numeric values.") from error
        present = values.dropna()
        if present.empty:
            raise ValueError(f"Feature column {name!r} contains no usable values.")
        if not np.isfinite(present).all():
            raise ValueError(f"Feature column {name!r} contains non-finite values.")
        if not present.between(0, 16).all():
            raise ValueError(f"Feature column {name!r} must contain values between 0 and 16.")
    if frame[target].isna().all():
        raise ValueError(f"Target column {target!r} has no usable values.")
    try:
        target_values = pd.to_numeric(frame[target], errors="raise")
    except (TypeError, ValueError) as error:
        raise ValueError(f"Target column {target!r} must contain numeric values.") from error
    if not target_values.notna().any():
        raise ValueError(f"Target column {target!r} has no numeric values.")
    present_targets = target_values.dropna()
    if not np.isfinite(present_targets).all():
        raise ValueError(f"Target column {target!r} contains non-finite values.")
    if not present_targets.between(0, 1).all():
        raise ValueError(f"Target column {target!r} must contain probabilities between 0 and 1.")
