import numpy as np
import pandas as pd
import pytest

from ml.preprocessing.feature_engineering import FLOOD_FEATURES, select_features


def test_feature_selection_uses_canonical_order() -> None:
    frame = pd.DataFrame([{name: 4.0 for name in reversed(FLOOD_FEATURES)}])

    selected = select_features(frame)

    assert tuple(selected.columns) == FLOOD_FEATURES
    assert selected.iloc[0].tolist() == [4.0] * len(FLOOD_FEATURES)


@pytest.mark.parametrize(
    ("invalid_value", "message"),
    [
        (np.nan, "missing values"),
        (np.inf, "non-finite"),
        (-0.1, "between 0 and 16"),
        (16.1, "between 0 and 16"),
        ("not-a-number", "numeric values"),
    ],
)
def test_feature_selection_rejects_missing_nonfinite_and_out_of_range_values(
    invalid_value: object,
    message: str,
) -> None:
    row = {name: 4.0 for name in FLOOD_FEATURES}
    row[FLOOD_FEATURES[0]] = invalid_value

    with pytest.raises(ValueError, match=message):
        select_features(pd.DataFrame([row]))


def test_feature_selection_rejects_missing_schema_columns() -> None:
    with pytest.raises(ValueError, match="missing required feature columns"):
        select_features(pd.DataFrame([{"MonsoonIntensity": 4.0}]))
