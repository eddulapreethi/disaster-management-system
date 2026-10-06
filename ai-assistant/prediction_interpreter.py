from collections.abc import Mapping, Sequence
from typing import Any

from .prompt_templates import FEATURE_NEGATIVE_TEMPLATE, FEATURE_POSITIVE_TEMPLATE, RISK_SUMMARY_TEMPLATE

HAZARD_LABELS = {
    "flood": "Flood",
    "wildfire": "Wildfire",
    "storm": "Storm",
}

FEATURE_LABELS = {
    "MonsoonIntensity": "Monsoon intensity",
    "TopographyDrainage": "Terrain drainage",
    "RiverManagement": "River management",
    "Deforestation": "Deforestation",
    "Urbanization": "Urbanization pressure",
    "ClimateChange": "Climate conditions",
    "DamsQuality": "Dam condition",
    "Siltation": "Siltation",
    "AgriculturalPractices": "Agricultural practices",
    "Encroachments": "Floodplain encroachment",
    "IneffectiveDisasterPreparedness": "Disaster preparedness",
    "DrainageSystems": "Drainage systems",
    "CoastalVulnerability": "Coastal vulnerability",
    "Landslides": "Landslide conditions",
    "Watersheds": "Watershed conditions",
    "DeterioratingInfrastructure": "Infrastructure condition",
    "PopulationScore": "Population exposure",
    "WetlandLoss": "Wetland loss",
    "InadequatePlanning": "Planning conditions",
    "PoliticalFactors": "Governance-related factors",
}


def interpret_prediction(
    prediction: Mapping[str, Any],
    contributions: Sequence[Mapping[str, Any]] | None = None,
    *,
    top_n: int = 3,
) -> dict[str, Any]:
    """Normalize a model prediction and explain its strongest SHAP factors."""
    if top_n < 0:
        raise ValueError("top_n cannot be negative.")
    hazard = str(prediction.get("disaster_type", "flood")).strip().lower()
    if hazard not in HAZARD_LABELS:
        raise ValueError(f"Unsupported disaster type: {hazard}")

    raw_score = prediction.get("risk_score")
    if raw_score is None and prediction.get("flood_probability") is not None:
        raw_score = float(prediction["flood_probability"]) * 100
    if raw_score is None:
        raise ValueError("Prediction must include risk_score or flood_probability.")
    score = float(raw_score)
    if not 0 <= score <= 100:
        raise ValueError("risk_score must be between 0 and 100.")

    risk_band = str(prediction.get("risk_band", prediction.get("risk_level", "unknown"))).lower()
    raw_contributions = contributions or prediction.get("top_contributions", [])
    if not isinstance(raw_contributions, Sequence) or isinstance(raw_contributions, (str, bytes)):
        raise ValueError("SHAP contributions must be a sequence of feature objects.")

    ranked = sorted(
        raw_contributions,
        key=lambda item: abs(float(item.get("shap_contribution", 0))),
        reverse=True,
    )[:top_n]
    factors = []
    for item in ranked:
        name = str(item.get("feature", "unknown"))
        label = FEATURE_LABELS.get(name, name.replace("_", " "))
        value = float(item.get("shap_contribution", 0))
        factors.append(
            {
                "feature": name,
                "label": label,
                "contribution": value,
                "direction": "increases" if value > 0 else "decreases" if value < 0 else "neutral",
            }
        )

    summary = RISK_SUMMARY_TEMPLATE.format(
        hazard=HAZARD_LABELS[hazard],
        risk_band=risk_band,
        risk_score=round(score, 1),
    )
    explanations = [
        (FEATURE_POSITIVE_TEMPLATE if factor["contribution"] > 0 else FEATURE_NEGATIVE_TEMPLATE).format(
            feature=factor["label"]
        )
        for factor in factors
        if factor["contribution"] != 0
    ]
    return {
        "disaster_type": hazard,
        "risk_score": score,
        "risk_band": risk_band,
        "summary": summary,
        "top_factors": factors,
        "factor_explanations": explanations,
        "model_explanation": prediction.get("explanation"),
    }
