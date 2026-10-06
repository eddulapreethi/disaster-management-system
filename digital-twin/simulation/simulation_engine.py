from typing import Protocol

from .simulation_model import DisasterType, SimulationResult, WeatherConditions, estimate_risk


class Scenario(Protocol):
    disaster_type: DisasterType
    name: str

    def apply(self, baseline: WeatherConditions) -> WeatherConditions: ...


def run_simulation(scenario: Scenario, baseline: WeatherConditions) -> SimulationResult:
    """Run one hazard scenario and compare it with the unchanged baseline."""
    if not scenario.name.strip():
        raise ValueError("Scenario name cannot be empty.")
    projected = scenario.apply(baseline)
    baseline_risk = estimate_risk(scenario.disaster_type, baseline)
    projected_risk = estimate_risk(scenario.disaster_type, projected)
    return SimulationResult(
        scenario_name=scenario.name,
        disaster_type=scenario.disaster_type,
        baseline_conditions=baseline.to_dict(),
        scenario_conditions=projected.to_dict(),
        baseline_risk_score=baseline_risk.score,
        baseline_risk_level=baseline_risk.level,
        scenario_risk_score=projected_risk.score,
        scenario_risk_level=projected_risk.level,
        score_change=round(projected_risk.score - baseline_risk.score, 2),
    )
