from typing import Any, Protocol

from sqlalchemy.orm import Session

from app.models.prediction import Prediction
from app.models.user import User
from app.schemas.prediction import PredictionCreate


class PredictionNotReadyError(ValueError):
    pass


class RiskInputs(Protocol):
    disaster_type: str
    rainfall_mm: float
    temperature_c: float
    wind_speed_kmh: float


def assess_risk(data: RiskInputs) -> tuple[float, str]:
    """Simple demonstrator heuristic; replace with a trained model for real forecasts."""
    if data.disaster_type == "flood":
        raise PredictionNotReadyError(
            "Flood prediction is unavailable: no validated trained model or verified runtime feature pipeline "
            "is installed. No score was calculated or saved."
        )
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
    if data.disaster_type == "flood":
        raise PredictionNotReadyError(
            "Flood prediction is unavailable: no validated trained model or verified runtime feature pipeline "
            "is installed. No score was calculated or saved."
        )

    prediction_inputs: RiskInputs = data
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
        "input_provenance": {"source": "client_supplied_environmental_inputs"},
    }

    prediction = Prediction(
        user_id=user.id,
        disaster_type=data.disaster_type,
        latitude=data.latitude,
        longitude=data.longitude,
        rainfall_mm=data.rainfall_mm,
        temperature_c=data.temperature_c,
        wind_speed_kmh=data.wind_speed_kmh,
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