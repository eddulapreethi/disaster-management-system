from sklearn.ensemble import RandomForestRegressor
from sklearn.pipeline import Pipeline

from ml.preprocessing.data_transformation import build_preprocessor


def build_disaster_prediction_model(
    *,
    n_estimators: int = 300,
    max_depth: int | None = None,
    random_state: int = 42,
) -> Pipeline:
    """Create the regression pipeline used to estimate flood probability."""
    regressor = RandomForestRegressor(
        n_estimators=n_estimators,
        max_depth=max_depth,
        min_samples_leaf=2,
        random_state=random_state,
        n_jobs=-1,
    )
    return Pipeline(
        steps=[
            ("preprocessor", build_preprocessor()),
            ("model", regressor),
        ]
    )
