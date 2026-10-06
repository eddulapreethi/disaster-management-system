from collections.abc import Iterable
from typing import Any

from ..simulation.simulation_engine import Scenario, run_simulation
from ..simulation.simulation_model import WeatherConditions


def evaluate_scenarios(
    baseline: WeatherConditions,
    scenarios: Iterable[Scenario],
) -> list[Any]:
    """Run each supplied what-if scenario against the same baseline."""
    return [run_simulation(scenario, baseline) for scenario in scenarios]


def rank_by_risk(results: Iterable[Any]) -> list[Any]:
    """Return simulation results ordered from highest to lowest projected risk."""
    return sorted(results, key=lambda result: result.scenario_risk_score, reverse=True)
