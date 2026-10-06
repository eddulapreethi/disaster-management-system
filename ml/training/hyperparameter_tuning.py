from sklearn.model_selection import GridSearchCV, KFold
from sklearn.pipeline import Pipeline


def tune_model(model: Pipeline, features, target, *, random_state: int = 42) -> GridSearchCV:
    """Tune a random-forest pipeline using cross-validated negative MAE."""
    folds = min(5, len(features))
    if folds < 2:
        raise ValueError("At least two training rows are required for cross-validation.")
    search = GridSearchCV(
        estimator=model,
        param_grid={
            "model__n_estimators": [200, 400],
            "model__max_depth": [None, 16],
            "model__min_samples_leaf": [1, 2, 4],
        },
        scoring="neg_mean_absolute_error",
        cv=KFold(n_splits=folds, shuffle=True, random_state=random_state),
        n_jobs=-1,
        refit=True,
    )
    search.fit(features, target)
    return search
