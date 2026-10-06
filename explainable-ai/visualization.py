from collections.abc import Sequence
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt


def plot_shap_contributions(
    contributions: Sequence[dict[str, Any]],
    output_path: str | Path,
    *,
    title: str = "Flood risk feature contributions (SHAP)",
) -> Path:
    """Save a horizontal plot of signed per-feature SHAP contributions."""
    if not contributions:
        raise ValueError("At least one SHAP contribution is required for a plot.")

    ordered = sorted(contributions, key=lambda item: abs(float(item["shap_contribution"])))
    labels = [str(item["feature"]).replace("_", " ") for item in ordered]
    values = [float(item["shap_contribution"]) for item in ordered]
    colors = ["#c2413b" if value >= 0 else "#167d78" for value in values]

    figure_height = max(3.0, 0.42 * len(ordered) + 1.2)
    figure, axis = plt.subplots(figsize=(9, figure_height), layout="constrained")
    axis.barh(labels, values, color=colors)
    axis.axvline(0, color="#333333", linewidth=0.8)
    axis.set_xlabel("Contribution to predicted flood probability")
    axis.set_title(title)
    axis.grid(axis="x", alpha=0.2)

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(destination, dpi=160)
    plt.close(figure)
    return destination
