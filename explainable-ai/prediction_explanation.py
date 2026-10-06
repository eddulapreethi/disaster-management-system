from collections.abc import Sequence
from typing import Any


def explain_prediction(
    probability: float,
    risk_band: str,
    contributions: Sequence[dict[str, Any]],
    *,
    top_n: int = 3,
) -> str:
    """Build a concise explanation from a predicted probability and SHAP factors."""
    if not 0.0 <= probability <= 1.0:
        raise ValueError("probability must be between 0 and 1.")
    if top_n < 1:
        raise ValueError("top_n must be at least 1.")

    probability_text = f"{probability:.1%}"
    if not contributions:
        return f"Estimated flood probability is {probability_text} ({risk_band} risk); no feature explanation is available."

    leading = sorted(
        contributions,
        key=lambda item: abs(float(item["shap_contribution"])),
        reverse=True,
    )[:top_n]
    factors = []
    for item in leading:
        feature = str(item["feature"]).replace("_", " ")
        contribution = float(item["shap_contribution"])
        direction = "increases" if contribution > 0 else "decreases" if contribution < 0 else "does not materially change"
        factors.append(f"{feature} {direction} the estimate")
    factor_text = "; ".join(factors)
    return f"Estimated flood probability is {probability_text} ({risk_band} risk). Main contributing factors: {factor_text}."
