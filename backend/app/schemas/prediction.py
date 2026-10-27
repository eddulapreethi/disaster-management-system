from datetime import datetime
import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from app.utils.utc_timestamps import utc_isoformat


class PredictionCreate(BaseModel):
    disaster_type: Literal["flood", "wildfire", "storm"]
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False, strict=True)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False, strict=True)
    weather_observation_id: int | None = Field(default=None, gt=0)
    rainfall_mm: float = Field(ge=0, le=2000, allow_inf_nan=False, strict=True)
    temperature_c: float = Field(ge=-100, le=100, allow_inf_nan=False, strict=True)
    wind_speed_kmh: float = Field(ge=0, le=500, allow_inf_nan=False, strict=True)
    features: dict[str, float] | None = None

    @field_validator("features")
    @classmethod
    def validate_features(cls, features: dict[str, float] | None) -> dict[str, float] | None:
        if features is None:
            return None
        if not features:
            raise ValueError("features cannot be empty.")
        if any(not name.strip() for name in features):
            raise ValueError("Feature names cannot be blank.")
        if any(not math.isfinite(value) or not 0 <= value <= 16 for value in features.values()):
            raise ValueError("Flood model feature values must be finite numbers between 0 and 16.")
        return features


class PredictionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    disaster_type: str
    latitude: float
    longitude: float
    rainfall_mm: float
    temperature_c: float
    wind_speed_kmh: float
    risk_score: float
    risk_level: str
    created_at: datetime

    @field_serializer("created_at", when_used="json")
    def serialize_created_at(self, value: datetime) -> str:
        return utc_isoformat(value) or ""


class PredictionResult(BaseModel):
    prediction: PredictionRead
    recommendations: list[str]
    model_source: Literal["trained_model", "weather_heuristic"]
    model_version: str | None = None
    target_value: float | None = None
    target_interpretation: Literal["continuous_index"] | None = None
    input_provenance: dict[str, str] = Field(default_factory=dict)
    risk_band: Literal["low", "medium", "high"]
    explanation: str
    top_contributions: list[dict[str, float | str]] = Field(default_factory=list)
    alert_generated: bool = False