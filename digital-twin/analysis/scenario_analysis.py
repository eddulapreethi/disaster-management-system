from collections.abc import Sequence
from typing import Any


def compare_results(results: Sequence[Any]) -> dict[str, Any]:
    """Summarize scenario risk deltas in descending order of projected risk."""
    scenarios = [
        {
            "scenario_name": result.scenario_name,
            "disaster_type": result.disaster_type,
            "baseline_risk_score": result.baseline_risk_score,
            "scenario_risk_score": result.scenario_risk_score,
            "baseline_risk_level": result.baseline_risk_level,
            "scenario_risk_level": result.scenario_risk_level,
            "score_change": result.score_change,
        }
        for result in results
    ]
    scenarios.sort(key=lambda item: item["scenario_risk_score"], reverse=True)
    return {
        "scenario_count": len(scenarios),
        "highest_risk_scenario": scenarios[0]["scenario_name"] if scenarios else None,
        "scenarios": scenarios,
        "note": "Comparative scenario estimates only; not an operational forecast.",
    }
