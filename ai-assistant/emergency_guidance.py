from collections.abc import Mapping, Sequence
from typing import Any

from .prompt_templates import ESTIMATE_DISCLAIMER

GUIDANCE: dict[str, dict[str, tuple[str, ...]]] = {
    "flood": {
        "low": (
            "Monitor official weather and local authority updates.",
            "Keep drains near your property clear where it is safe to do so.",
        ),
        "moderate": (
            "Avoid walking or driving through floodwater.",
            "Charge communication devices and prepare essential medicines and documents.",
            "Know the official route to higher ground or a designated shelter.",
        ),
        "high": (
            "Follow local authority instructions and evacuate if directed.",
            "Move people and essential items to higher ground when safe; never enter floodwater.",
            "If trapped by rising water, move to the highest safe level and contact emergency services.",
        ),
        "critical": (
            "Treat this as a serious modeled risk and check official alerts immediately.",
            "Evacuate only according to official guidance and use designated safe routes.",
            "Do not enter floodwater; contact emergency services if in immediate danger.",
        ),
    },
    "wildfire": {
        "low": (
            "Monitor official fire and air-quality updates.",
            "Keep outdoor areas clear of dry combustible material where permitted and safe.",
        ),
        "moderate": (
            "Prepare essential items and identify more than one route away from the area.",
            "Keep windows closed if smoke is present and follow public-health advice.",
            "Do not light outdoor fires or burn vegetation during dry conditions.",
        ),
        "high": (
            "Follow evacuation orders promptly; do not wait for visible flames.",
            "Leave using official routes and avoid driving toward smoke or fire.",
            "If evacuation is not possible, contact emergency services and follow their instructions.",
        ),
        "critical": (
            "Check official emergency alerts now and evacuate if instructed.",
            "Avoid smoke and fire areas; do not attempt to fight a spreading wildfire yourself.",
            "Call emergency services if you are trapped or in immediate danger.",
        ),
    },
    "storm": {
        "low": (
            "Monitor official weather forecasts and alerts.",
            "Secure loose outdoor objects when conditions are safe.",
        ),
        "moderate": (
            "Stay indoors away from windows during severe winds or lightning.",
            "Charge devices and keep a flashlight, water, and essential medicines available.",
            "Avoid coastal, flood-prone, and exposed areas if authorities advise staying away.",
        ),
        "high": (
            "Follow official shelter or evacuation instructions.",
            "Stay inside a sturdy building and avoid windows; do not shelter under trees.",
            "Never drive through floodwater or around emergency road closures.",
        ),
        "critical": (
            "Check official warnings immediately and follow emergency instructions.",
            "Move to a designated safe shelter if directed and stay away from windows.",
            "Contact emergency services if you are injured, trapped, or facing immediate danger.",
        ),
    },
}


def get_emergency_guidance(
    disaster_type: str,
    risk_level: str,
    *,
    simulation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return hazard-specific preparedness guidance without claiming official authority."""
    hazard = disaster_type.strip().lower()
    if hazard not in GUIDANCE:
        raise ValueError(f"Unsupported disaster type: {disaster_type}")
    level = risk_level.strip().lower()
    if level not in {"low", "moderate", "medium", "high", "critical"}:
        raise ValueError(f"Unsupported risk level: {risk_level}")
    if level == "medium":
        level = "moderate"

    actions = list(GUIDANCE[hazard][level])
    scenario_summary = None
    if simulation:
        scenario_type = str(simulation.get("disaster_type", hazard)).lower()
        if scenario_type != hazard:
            raise ValueError("Simulation hazard does not match the requested guidance hazard.")
        scenario_level = str(simulation.get("scenario_risk_level", "")).lower()
        if scenario_level in {"high", "critical"} and level in {"low", "moderate"}:
            actions = list(GUIDANCE[hazard]["high"])
        scenario_name = simulation.get("scenario_name")
        if scenario_name:
            scenario_summary = f"Scenario considered: {scenario_name}. Scenario output is an estimate only."

    return {
        "disaster_type": hazard,
        "risk_level": level,
        "actions": actions,
        "scenario_context": scenario_summary,
        "disclaimer": ESTIMATE_DISCLAIMER,
    }
