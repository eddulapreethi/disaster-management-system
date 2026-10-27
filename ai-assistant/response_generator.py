from collections.abc import Mapping, Sequence
from typing import Any

from .prompt_templates import ESTIMATE_DISCLAIMER, SCENARIO_SUMMARY_TEMPLATE
from .recommendation_engine import generate_recommendations


def generate_response(
    prediction: Mapping[str, Any],
    *,
    shap_contributions: Sequence[Mapping[str, Any]] | None = None,
    simulation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a user-facing response and machine-readable recommendation payload."""
    result = generate_recommendations(
        prediction,
        shap_contributions=shap_contributions,
        simulation=simulation,
    )
    paragraphs = [result["summary"]]
    if result["simulation_summary"]:
        paragraphs.append(result["simulation_summary"])
    if result["top_factors"]:
        factors = ", ".join(factor["label"] for factor in result["top_factors"][:3])
        paragraphs.append(f"Main model factors: {factors}.")
    paragraphs.append("Recommended next steps: " + " ".join(result["recommendations"]))
    paragraphs.append(ESTIMATE_DISCLAIMER)
    result["response"] = " ".join(paragraphs)
    return result


def generate_scenario_response(
    simulation: Mapping[str, Any],
    *,
    disaster_type: str | None = None,
) -> dict[str, Any]:
    """Create a response for a scenario result when no ML prediction is supplied."""
    hazard = (disaster_type or str(simulation.get("disaster_type", ""))).lower()
    if not hazard:
        raise ValueError("A disaster_type is required in the simulation or function arguments.")

    score = float(simulation.get("scenario_risk_score", simulation.get("simulated_risk_score", -1)))
    if not 0 <= score <= 100:
        raise ValueError("Simulation risk score must be between 0 and 100.")
    level = str(
        simulation.get("scenario_risk_level", simulation.get("simulated_risk_level", ""))
    ).lower()
    if not level:
        level = "low" if score < 30 else "moderate" if score < 60 else "high" if score < 80 else "critical"

    from .emergency_guidance import get_emergency_guidance

    guidance = get_emergency_guidance(hazard, level, simulation=simulation)
    name = str(simulation.get("scenario_name", "what-if scenario"))
    baseline_score = float(simulation.get("baseline_risk_score", score))
    change = float(simulation.get("score_change", score - baseline_score))
    summary = SCENARIO_SUMMARY_TEMPLATE.format(
        scenario_name=name,
        baseline_score=baseline_score,
        scenario_score=score,
        score_change=change,
    )
    response = f"{summary} Recommended next steps: {' '.join(guidance['actions'])} {ESTIMATE_DISCLAIMER}"
    return {
        "disaster_type": hazard,
        "risk_score": score,
        "risk_band": level,
        "summary": summary,
        "simulation_summary": summary,
        "top_factors": [],
        "recommendations": guidance["actions"],
        "disclaimer": ESTIMATE_DISCLAIMER,
        "response": response,
    }


def generate_general_preparedness_response() -> dict[str, Any]:
    """Provide preparedness guidance without implying a location-specific prediction."""
    recommendations = [
        "Follow official local emergency alerts and instructions.",
        "Keep essential medicines, water, identification, and a charged phone accessible.",
        "Know how to contact local emergency services and where official shelters are located.",
        "Do not enter floodwater, fire, or unsafe structures; leave danger areas when authorities advise.",
    ]
    summary = "General preparedness guidance — no validated location-specific prediction is available."
    return {
        "disaster_type": None,
        "risk_score": None,
        "risk_band": "unknown",
        "summary": summary,
        "simulation_summary": None,
        "top_factors": [],
        "recommendations": recommendations,
        "disclaimer": (
            "General preparedness information only; not a forecast, official warning, or guidance based on a confirmed local hazard."
        ),
        "response": " ".join([summary, *recommendations]),
    }
