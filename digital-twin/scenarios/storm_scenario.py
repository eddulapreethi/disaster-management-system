from dataclasses import dataclass
from typing import ClassVar, Literal

from ..simulation.simulation_model import WeatherConditions


@dataclass(frozen=True)
class StormScenario:
    disaster_type: ClassVar[Literal["storm"]] = "storm"
    rainfall_change_percent: float = 0.0
    wind_change_percent: float = 0.0
    name: str = "Storm scenario"

    def __post_init__(self) -> None:
        for field_name, change in (
            ("rainfall_change_percent", self.rainfall_change_percent),
            ("wind_change_percent", self.wind_change_percent),
        ):
            if not -100 <= change <= 1000:
                raise ValueError(f"{field_name} must be between -100 and 1000.")

    def apply(self, baseline: WeatherConditions) -> WeatherConditions:
        rainfall = baseline.rainfall_mm * (1 + self.rainfall_change_percent / 100)
        wind_speed = baseline.wind_speed_kmh * (1 + self.wind_change_percent / 100)
        return WeatherConditions(rainfall_mm=rainfall, temperature_c=baseline.temperature_c, wind_speed_kmh=wind_speed)
