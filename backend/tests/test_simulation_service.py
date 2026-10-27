import pytest
from pydantic import ValidationError

from app.services.simulation_service import SimulationInput, run_simulation


def test_flood_scenario_change_matches_the_demonstrator_formula() -> None:
    result = run_simulation(
        SimulationInput(
            disaster_type="flood",
            latitude=9.9,
            longitude=76.2,
            rainfall_change_percent=100,
        ),
        {"precipitation_mm": 20, "temperature_c": 25, "wind_speed_kmh": 0},
    )

    assert result["baseline_risk_score"] == 16
    assert result["scenario_risk_score"] == 32
    assert result["score_change"] == result["scenario_risk_score"] - result["baseline_risk_score"]
    assert "not an official warning" in result["note"]
    assert "zero score does not establish zero disaster risk" in result["note"]


def test_flood_scenario_can_add_hypothetical_rain_when_current_precipitation_is_zero() -> None:
    result = run_simulation(
        SimulationInput(
            disaster_type="flood",
            latitude=0,
            longitude=0,
            additional_rainfall_mm=20,
        ),
        {"precipitation_mm": 0, "temperature_c": 25, "wind_speed_kmh": 0},
    )

    assert result["baseline_risk_score"] == 0
    assert result["scenario_risk_score"] == 16
    assert result["score_change"] == 16


def test_simulation_zero_is_reported_as_a_formula_result_not_no_risk() -> None:
    result = run_simulation(
        SimulationInput(disaster_type="flood", latitude=-90, longitude=-180),
        {"precipitation_mm": 0, "temperature_c": 25, "wind_speed_kmh": 0},
    )

    assert result["baseline_risk_score"] == 0
    assert result["scenario_risk_score"] == 0
    assert "does not establish zero disaster risk" in result["note"]


def test_simulation_rejects_nonfinite_and_out_of_range_inputs() -> None:
    with pytest.raises(ValidationError):
        SimulationInput(disaster_type="flood", latitude=float("nan"), longitude=0)
    with pytest.raises(ValidationError):
        SimulationInput(disaster_type="flood", latitude=90.01, longitude=0)
    with pytest.raises(ValidationError):
        SimulationInput(disaster_type="flood", latitude=0, longitude=180.01)
    with pytest.raises(ValidationError):
        SimulationInput(disaster_type="flood", latitude=0, longitude=0, additional_rainfall_mm=501)
    with pytest.raises(ValidationError):
        SimulationInput(disaster_type="storm", latitude=0, longitude=0, additional_rainfall_mm=1)
    with pytest.raises(ValidationError):
        SimulationInput(disaster_type="earthquake")
