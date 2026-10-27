from collections.abc import Mapping
import importlib
from pathlib import Path
import sys
from typing import Any

from pydantic import BaseModel, Field, model_validator


class SimulationInput(BaseModel):
    disaster_type: str = Field(pattern="^(flood|wildfire|storm)$")
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False, strict=True)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False, strict=True)
    rainfall_change_percent: float = Field(default=0, ge=-100, le=500, allow_inf_nan=False, strict=True)
    additional_rainfall_mm: float = Field(default=0, ge=0, le=500, allow_inf_nan=False, strict=True)
    wind_change_percent: float = Field(default=0, ge=-100, le=500, allow_inf_nan=False, strict=True)
    temperature_change_c: float = Field(default=0, ge=-100, le=100, allow_inf_nan=False, strict=True)

    @model_validator(mode="after")
    def reject_inapplicable_parameters(self) -> "SimulationInput":
        if self.disaster_type != "flood" and self.additional_rainfall_mm:
            raise ValueError("Additional rainfall is only supported for flood scenarios.")
        if self.disaster_type not in {"storm", "wildfire"} and self.wind_change_percent:
            raise ValueError("Wind change is only supported for storm and wildfire scenarios.")
        if self.disaster_type != "wildfire" and self.temperature_change_c:
            raise ValueError("Temperature change is only supported for wildfire scenarios.")
        return self


def run_simulation(data: SimulationInput, weather: Mapping[str, Any]) -> dict:
    project_root = str(Path(__file__).resolve().parents[3])
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    model = importlib.import_module("digital-twin.simulation.simulation_model")
    engine = importlib.import_module("digital-twin.simulation.simulation_engine")
    scenarios = {
        "flood": importlib.import_module("digital-twin.scenarios.flood_scenario").FloodScenario,
        "storm": importlib.import_module("digital-twin.scenarios.storm_scenario").StormScenario,
        "wildfire": importlib.import_module("digital-twin.scenarios.wildfire_scenario").WildfireScenario,
    }
    baseline = model.WeatherConditions(
        rainfall_mm=weather["precipitation_mm"],
        temperature_c=weather["temperature_c"],
        wind_speed_kmh=weather["wind_speed_kmh"],
    )
    scenario_options = {
        "rainfall_change_percent": data.rainfall_change_percent,
        "name": f"{data.disaster_type.title()} what-if scenario",
    }
    if data.disaster_type == "storm":
        scenario_options["wind_change_percent"] = data.wind_change_percent
    elif data.disaster_type == "flood":
        scenario_options["upstream_rainfall_mm"] = data.additional_rainfall_mm
    elif data.disaster_type == "wildfire":
        scenario_options["wind_change_percent"] = data.wind_change_percent
        scenario_options["temperature_change_c"] = data.temperature_change_c
    scenario = scenarios[data.disaster_type](**scenario_options)
    return engine.run_simulation(scenario, baseline).to_dict()