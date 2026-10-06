import importlib
import sys
from pathlib import Path

from pydantic import BaseModel, Field


class SimulationInput(BaseModel):
    disaster_type: str = Field(pattern="^(flood|wildfire|storm)$")
    rainfall_mm: float = Field(default=0, ge=0, le=2000)
    temperature_c: float = Field(default=25, ge=-100, le=100)
    wind_speed_kmh: float = Field(default=0, ge=0, le=500)
    rainfall_change_percent: float = Field(default=0, ge=-100, le=500)
    wind_change_percent: float = Field(default=0, ge=-100, le=500)
    temperature_change_c: float = Field(default=0, ge=-100, le=100)


def run_simulation(data: SimulationInput) -> dict:
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
        rainfall_mm=data.rainfall_mm,
        temperature_c=data.temperature_c,
        wind_speed_kmh=data.wind_speed_kmh,
    )
    scenario_options = {
        "rainfall_change_percent": data.rainfall_change_percent,
        "name": f"{data.disaster_type.title()} what-if scenario",
    }
    if data.disaster_type == "storm":
        scenario_options["wind_change_percent"] = data.wind_change_percent
    elif data.disaster_type == "wildfire":
        scenario_options["wind_change_percent"] = data.wind_change_percent
        scenario_options["temperature_change_c"] = data.temperature_change_c
    scenario = scenarios[data.disaster_type](**scenario_options)
    return engine.run_simulation(scenario, baseline).to_dict()