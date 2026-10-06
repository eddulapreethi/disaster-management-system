def classify_risk(probability: float) -> tuple[float, str]:
    """Convert flood probability (0..1) into the dashboard score and risk band."""
    bounded_probability = min(1.0, max(0.0, float(probability)))
    score = round(bounded_probability * 100, 2)
    band = "low" if score < 45 else "medium" if score < 65 else "high"
    return score, band
