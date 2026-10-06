from dataclasses import dataclass
from typing import ClassVar, Literal

from ..simulation.simulation_model import WeatherConditions


@dataclass(frozen=True)
class FloodScenario:
    disaster_type: ClassVar[Literal["flood"]] = "flood"
    rainfall_change_percent: float = 0.0
    upstream_rainfall_mm: float = 0.0
    name: str = "Flood scenario"

    def __post_init__(self) -> None:
        if not -100 <= self.rainfall_change_percent <= 1000:
            raise ValueError("rainfall_change_percent must be between -100 and 1000.")
        if self.upstream_rainfall_mm < 0:
            raise ValueError("upstream_rainfall_mm cannot be negative.")

    def apply(self, baseline: WeatherConditions) -> WeatherConditions:
        rainfall = baseline.rainfall_mm * (1 + self.rainfall_change_percent / 100) + self.upstream_rainfall_mm
        return WeatherConditions(rainfall_mm=rainfall, temperature_c=baseline.temperature_c, wind_speed_kmh=baseline.wind_speed_kmh)
