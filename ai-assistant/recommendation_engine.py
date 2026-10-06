from collections.abc import Mapping, Sequence
from typing import Any

from .emergency_guidance import get_emergency_guidance
from .prediction_interpreter import interpret_prediction
from .prompt_templates import ESTIMATE_DISCLAIMER, SCENARIO_SUMMARY_TEMPLATE


def generate_recommendations(
    prediction: Mapping[str, Any],
    *,
    shap_contributions: Sequence[Mapping[str, Any]] | None = None,
    simulation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Combine prediction, SHAP and optional simulation evidence into guidance."""
    interpretation = interpret_prediction(prediction, shap_contributions)
    hazard = interpretation["disaster_type"]
    risk_level = interpretation["risk_band"]
    if risk_level == "unknown":
        score = interpretation["risk_score"]
        risk_level = "low" if score < 30 else "moderate" if score < 60 else "high" if score < 80 else "critical"

    simulation_summary = None
    guidance_risk_level = risk_level
    if simulation is not None:
        simulation_hazard = str(simulation.get("disaster_type", hazard)).lower()
        if simulation_hazard != hazard:
            raise ValueError("Simulation hazard must match the prediction hazard.")
        scenario_score = float(simulation.get("scenario_risk_score", simulation.get("simulated_risk_score", -1)))
        if not 0 <= scenario_score <= 100:
            raise ValueError("Simulation risk score must be between 0 and 100.")
        scenario_level = str(
            simulation.get("scenario_risk_level", simulation.get("simulated_risk_level", "unknown"))
        ).lower()
        if scenario_level == "unknown":
            scenario_level = "low" if scenario_score < 30 else "moderate" if scenario_score < 60 else "high" if scenario_score < 80 else "critical"
        guidance_risk_level = max((risk_level, scenario_level), key=_risk_rank)
        simulation_summary = SCENARIO_SUMMARY_TEMPLATE.format(
            scenario_name=str(simulation.get("scenario_name", "what-if scenario")),
            baseline_score=float(simulation.get("baseline_risk_score", interpretation["risk_score"])),
            scenario_score=scenario_score,
            score_change=float(simulation.get("score_change", scenario_score - interpretation["risk_score"])),
        )

    guidance = get_emergency_guidance(hazard, guidance_risk_level, simulation=simulation)
    actions = list(guidance["actions"])
    top_factors = interpretation["top_factors"]
    if top_factors:
        leading = top_factors[0]
        if leading["direction"] == "increases":
            actions.insert(0, f"Pay particular attention to {leading['label']}, which most strongly increases this model estimate.")

    return {
        "disaster_type": hazard,
        "risk_score": interpretation["risk_score"],
        "risk_band": risk_level,
        "summary": interpretation["summary"],
        "simulation_summary": simulation_summary,
        "top_factors": top_factors,
        "recommendations": actions,
        "disclaimer": ESTIMATE_DISCLAIMER,
    }


def _risk_rank(level: str) -> int:
    return {"low": 0, "moderate": 1, "medium": 1, "high": 2, "critical": 3}.get(level, -1)
