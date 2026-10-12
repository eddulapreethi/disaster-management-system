import pytest
from pydantic import ValidationError

from app.services.simulation_service import SimulationInput, run_simulation


def test_flood_scenario_change_matches_the_demonstrator_formula() -> None:
    result = run_simulation(
        SimulationInput(
            disaster_type="flood",
            rainfall_mm=20,
            rainfall_change_percent=100,
        )
    )

    assert result["baseline_risk_score"] == 16
    assert result["scenario_risk_score"] == 32
    assert result["score_change"] == result["scenario_risk_score"] - result["baseline_risk_score"]
    assert "not an official warning" in result["note"]


def test_simulation_rejects_nonfinite_and_out_of_range_inputs() -> None:
    with pytest.raises(ValidationError):
        SimulationInput(disaster_type="flood", rainfall_mm=float("nan"))
    with pytest.raises(ValidationError):
        SimulationInput(disaster_type="flood", rainfall_mm=2001)
    with pytest.raises(ValidationError):
        SimulationInput(disaster_type="earthquake")
