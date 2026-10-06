import os
import sys
from pathlib import Path
from typing import Any, Protocol

from sqlalchemy.orm import Session

from app.models.prediction import Prediction
from app.models.user import User
from app.schemas.prediction import PredictionCreate


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
    model_output: dict[str, Any] | None = None
    if data.disaster_type == "flood" and data.features:
        try:
            project_root = str(Path(__file__).resolve().parents[3])
            if project_root not in sys.path:
                sys.path.insert(0, project_root)
            from ml.prediction.predict import predict_risk

            model_path = os.getenv("DISASTERGUARD_MODEL_PATH")
            model_output = predict_risk(data.features, model_path=model_path) if model_path else predict_risk(data.features)
        except FileNotFoundError:
            model_output = None
        except ModuleNotFoundError:
            model_output = None

    if model_output is not None:
        score = round(float(model_output["risk_score"]), 2)
        level = classify_persisted_risk(score)
        details = {
            "model_source": "trained_model",
            "risk_band": model_output["risk_band"],
            "explanation": model_output["explanation"],
            "top_contributions": model_output["top_contributions"],
        }
    else:
        score, level = assess_risk(data)
        details = {
            "model_source": "weather_heuristic",
            "risk_band": "low" if score < 45 else "medium" if score < 65 else "high",
            "explanation": (
                "No trained flood model artifact is available; this result uses the "
                "backend's demonstrator weather heuristic and has no SHAP explanation."
            ),
            "top_contributions": [],
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


def classify_persisted_risk(score: float) -> str:
    return "low" if score < 30 else "moderate" if score < 60 else "high" if score < 80 else "critical"


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