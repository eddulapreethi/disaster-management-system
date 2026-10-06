from ml.models.risk_classification import classify_risk


def assess_risk(probability: float) -> dict[str, float | str]:
    """Return dashboard-compatible risk score and risk band."""
    score, band = classify_risk(probability)
    return {
        "flood_probability": min(1.0, max(0.0, float(probability))),
        "risk_score": score,
        "risk_band": band,
    }
