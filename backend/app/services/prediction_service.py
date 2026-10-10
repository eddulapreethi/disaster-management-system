from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Protocol

from sqlalchemy.orm import Session

from app.models.prediction import Prediction
from app.models.user import User
from app.models.weather_observation import WeatherObservation
from app.schemas.prediction import PredictionCreate
from app.services.weather_service import get_max_age_seconds


class RiskInputs(Protocol):
    disaster_type: str
    rainfall_mm: float
    temperature_c: float
    wind_speed_kmh: float


def assess_risk(data: RiskInputs) -> tuple[float, str]:
    """Simple demonstrator heuristic; replace with a trained model for real forecasts."""
    if data.disaster_type == "flood":
        score = min(100, data.rainfall_mm * 0.8)
    elif data.disaster_type == "wildfire":
        heat = max(0, data.temperature_c - 20) * 1.5
        wind = data.wind_speed_kmh * 0.35
        dryness = max(0, 100 - data.rainfall_mm) * 0.25
        score = min(100, heat + wind + dryness)
    else:  # storm
        score = min(100, data.wind_speed_kmh * 0.8 + data.rainfall_mm * 0.25)

    score = round(max(0, score), 2)
    level = "low" if score < 30 else "moderate" if score < 60 else "high" if score < 80 else "critical"
    return score, level


def create_prediction(db: Session, user: User, data: PredictionCreate) -> tuple[Prediction, dict[str, Any]]:
    if data.disaster_type == "flood" and data.features:
        raise ValueError(
            "Flood ML inference is disabled until a validated feature-source mapping is installed; "
            "manually supplied 0-16 indices are not accepted."
        )
    prediction_inputs: RiskInputs = data
    stored_weather: WeatherObservation | None = None
    input_provenance: dict[str, str] = {"source": "client_supplied_environmental_inputs"}
    if data.disaster_type == "flood":
        if data.weather_observation_id is None:
            raise ValueError(
                "A stored location-matched weather_observation_id is required; client-entered or default weather is not accepted."
            )
        stored_weather = db.get(WeatherObservation, data.weather_observation_id)
        if stored_weather is None:
            raise ValueError("The selected weather observation is not present in the backend database.")
        distance_squared = (
            (stored_weather.latitude - data.latitude) ** 2
            + (stored_weather.longitude - data.longitude) ** 2
        )
        if distance_squared > 0.0004:
            raise ValueError("The selected weather observation does not match the prediction location.")
        observation_time = stored_weather.observation_time
        if observation_time.tzinfo is None:
            observation_time = observation_time.replace(tzinfo=timezone.utc)
        age_seconds = (datetime.now(timezone.utc) - observation_time.astimezone(timezone.utc)).total_seconds()
        try:
            max_age_seconds = get_max_age_seconds()
        except RuntimeError as error:
            raise ValueError("The configured weather freshness window is invalid.") from error
        if age_seconds < -300 or age_seconds > max_age_seconds:
            raise ValueError("The selected weather observation is not within the configured freshness window.")
        rainfall = stored_weather.rain_mm
        if rainfall is None:
            rainfall = stored_weather.precipitation_mm
        if rainfall is None or stored_weather.temperature_c is None or stored_weather.wind_speed_kmh is None:
            raise ValueError(
                "The stored weather observation is missing rainfall, temperature, or wind; no prediction was saved."
            )
        prediction_inputs = SimpleNamespace(
            disaster_type=data.disaster_type,
            rainfall_mm=rainfall,
            temperature_c=stored_weather.temperature_c,
            wind_speed_kmh=stored_weather.wind_speed_kmh,
        )
        input_provenance = {
            "source": stored_weather.source,
            "station_name": stored_weather.station_name,
            "observation_time": stored_weather.observation_time.isoformat(),
            "fetched_at": stored_weather.fetched_at.isoformat(),
        }

    score, level = assess_risk(prediction_inputs)
    details = {
        "model_source": "weather_heuristic",
        "risk_band": "low" if score < 45 else "medium" if score < 65 else "high",
        "explanation": (
            "No compatible trained flood model and validated input pipeline are available; this result uses an "
            "unvalidated demonstrator weather heuristic, not a forecast or probability, and has no SHAP explanation."
        ),
        "top_contributions": [],
        "model_version": None,
        "target_value": None,
        "target_interpretation": None,
        "input_provenance": input_provenance,
    }

    prediction = Prediction(
        user_id=user.id,
        disaster_type=data.disaster_type,
        latitude=data.latitude,
        longitude=data.longitude,
        rainfall_mm=prediction_inputs.rainfall_mm,
        temperature_c=prediction_inputs.temperature_c,
        wind_speed_kmh=prediction_inputs.wind_speed_kmh,
        risk_score=score,
        risk_level=level,
    )
    db.add(prediction)
    db.commit()
    db.refresh(prediction)
    return prediction, details


def get_recommendations(disaster_type: str, risk_level: str) -> list[str]:
    if risk_level in {"high", "critical"}:
        return [
            "Follow official local emergency instructions.",
            "Prepare essential medication, water, and identification.",
            "Move to a safer location if authorities advise evacuation.",
        ]
    if disaster_type == "flood":
        return ["Monitor local weather updates.", "Avoid walking or driving through floodwater."]
    if disaster_type == "wildfire":
        return ["Monitor fire and air-quality updates.", "Keep evacuation routes accessible."]
    return ["Monitor official weather alerts.", "Secure loose objects outdoors."]