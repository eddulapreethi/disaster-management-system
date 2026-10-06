from ml.evaluation.metrics import regression_metrics


def evaluate_model(model, features, target) -> dict[str, float | None]:
    """Run a fitted model on held-out rows and return regression metrics."""
    predictions = model.predict(features)
    return regression_metrics(target, predictions)
