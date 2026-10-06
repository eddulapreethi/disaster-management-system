from dataclasses import dataclass
from typing import ClassVar, Literal

from ..simulation.simulation_model import WeatherConditions


@dataclass(frozen=True)
class WildfireScenario:
    disaster_type: ClassVar[Literal["wildfire"]] = "wildfire"
    temperature_change_c: float = 0.0
    wind_change_percent: float = 0.0
    rainfall_change_percent: float = 0.0
    name: str = "Wildfire scenario"

    def __post_init__(self) -> None:
        if not -100 <= self.temperature_change_c <= 100:
            raise ValueError("temperature_change_c must be between -100 and 100.")
        for field_name, change in (
            ("wind_change_percent", self.wind_change_percent),
            ("rainfall_change_percent", self.rainfall_change_percent),
        ):
            if not -100 <= change <= 1000:
                raise ValueError(f"{field_name} must be between -100 and 1000.")

    def apply(self, baseline: WeatherConditions) -> WeatherConditions:
        return WeatherConditions(
            rainfall_mm=baseline.rainfall_mm * (1 + self.rainfall_change_percent / 100),
            temperature_c=baseline.temperature_c + self.temperature_change_c,
            wind_speed_kmh=baseline.wind_speed_kmh * (1 + self.wind_change_percent / 100),
        )
