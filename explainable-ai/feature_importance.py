from collections.abc import Sequence
from typing import Any


def rank_feature_importance(
    contributions: Sequence[dict[str, Any]],
    *,
    limit: int | None = 5,
) -> list[dict[str, Any]]:
    """Return SHAP contributions ordered by absolute impact, retaining direction."""
    if limit is not None and limit < 0:
        raise ValueError("limit must be non-negative or None.")
    ranked = sorted(
        contributions,
        key=lambda item: abs(float(item["shap_contribution"])),
        reverse=True,
    )
    return ranked if limit is None else ranked[:limit]
