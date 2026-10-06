from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Literal

DisasterType = Literal["flood", "wildfire", "storm"]


@dataclass(frozen=True)
class WeatherConditions:
    """Weather inputs consumed by the scenario risk estimator."""

    rainfall_mm: float = 0.0
    temperature_c: float = 25.0
    wind_speed_kmh: float = 0.0

    def __post_init__(self) -> None:
        values = (self.rainfall_mm, self.temperature_c, self.wind_speed_kmh)
        if not all(math.isfinite(value) for value in values):
            raise ValueError("Weather inputs must be finite numbers.")
        if self.rainfall_mm < 0 or self.wind_speed_kmh < 0:
            raise ValueError("Rainfall and wind speed cannot be negative.")

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


@dataclass(frozen=True)
class RiskEstimate:
    score: float
    level: str


def estimate_risk(disaster_type: DisasterType, conditions: WeatherConditions) -> RiskEstimate:
    """Estimate risk using the same demonstrator formulas as the backend service."""
    if disaster_type == "flood":
        score = min(100.0, conditions.rainfall_mm * 0.8)
    elif disaster_type == "wildfire":
        heat = max(0.0, conditions.temperature_c - 20.0) * 1.5
        wind = conditions.wind_speed_kmh * 0.35
        dryness = max(0.0, 100.0 - conditions.rainfall_mm) * 0.25
        score = min(100.0, heat + wind + dryness)
    elif disaster_type == "storm":
        score = min(100.0, conditions.wind_speed_kmh * 0.8 + conditions.rainfall_mm * 0.25)
    else:
        raise ValueError(f"Unsupported disaster type: {disaster_type}")

    bounded_score = round(max(0.0, score), 2)
    level = "low" if bounded_score < 30 else "moderate" if bounded_score < 60 else "high" if bounded_score < 80 else "critical"
    return RiskEstimate(score=bounded_score, level=level)


@dataclass(frozen=True)
class SimulationResult:
    scenario_name: str
    disaster_type: DisasterType
    baseline_conditions: dict[str, float]
    scenario_conditions: dict[str, float]
    baseline_risk_score: float
    baseline_risk_level: str
    scenario_risk_score: float
    scenario_risk_level: str
    score_change: float
    note: str = "Scenario estimate only; not an official warning or operational forecast."

    def to_dict(self) -> dict[str, str | float | dict[str, float]]:
        return asdict(self)
