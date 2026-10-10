from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.models.prediction import Prediction
from app.models.resource import Resource
from app.models.simulation import Simulation
from app.models.user import User
from app.models.weather_observation import WeatherObservation
from app.services.data_readiness_service import get_data_readiness, get_hydrology_status

ASSISTANT_DISCLAIMER = (
    "DisasterGuard is a decision-support tool, not an emergency authority. "
    "For urgent situations, follow official local emergency services."
)

GENERAL_ANSWERS = (
    (("flood",), "A flood is an overflow of water onto land that is usually dry. It can result from intense or prolonged rainfall, river overflow, storm surge, rapid snow or ice melt, or drainage failure."),
    (("cyclone", "hurricane", "typhoon", "storm"), "A tropical cyclone is an organized rotating storm that forms over warm ocean water. It can bring damaging winds, heavy rain, coastal surge, and flooding. Regional names differ; use official local forecasts for current warnings."),
    (("landslide", "mudslide"), "A landslide is the movement of rock, soil, or debris down a slope. Triggers can include intense rain, earthquakes, erosion, and slope disturbance. Local authorities determine whether an area is unsafe."),
    (("wildfire", "forest fire"), "A wildfire is an uncontrolled fire in vegetation. Weather, dry fuel, terrain, and ignition sources affect its spread. Follow official evacuation and air-quality instructions."),
    (("preparedness", "prepare for", "emergency kit"), "Disaster preparedness includes knowing local alerts and evacuation guidance, keeping essential medication and supplies accessible, making a household communication plan, and following official instructions."),
    (("gis", "geographic information system"), "GIS (a geographic information system) stores, analyzes, and displays information tied to locations. Disaster teams can use maps to understand hazards, exposed places, and resources."),
    (("digital twin", "simulation"), "A Digital Twin is a digital representation used to explore how a system may respond to changed assumptions. DisasterGuard's what-if simulation is a heuristic scenario estimate, not a physical forecast or a trained ML prediction."),
    (("shap",), "SHAP (SHapley Additive exPlanations) attributes a model prediction across its input features. DisasterGuard only provides SHAP contributions when a compatible trained model artifact is available; it does not invent explanations when the model is unavailable."),
    (("machine learning", " ml ", "model"), "Machine learning fits a model to examples and uses the learned patterns on new inputs. A risk model is only meaningful when its features, labels, training data, and evaluation are valid and representative."),
    (("dashboard", "ready mean", "readiness"), "The dashboard reports component readiness from stored source observations and configured model/feature availability. READY is specific to each component; it is not an official warning or a guarantee that a hazard will occur."),
)

PROJECT_ANSWERS = (
    (("data source", "what data", "collected"), "The backend stores current weather observations from Open-Meteo and hydrological telemetry from configured NWDP/NWIC CWC resources. Collection checks run periodically; duplicate source observations are skipped. Copernicus Sentinel catalog/image endpoints are available when credentials are configured, but satellite-derived model features are not currently produced."),
    (("hydrology stale", "why hydrology", "hydrology status"), None),
    (("shap", "explanation"), None),
    (("model", "trained"), None),
    (("score", "risk score", "prediction"), "A displayed score is an application estimate on a 0–100 scale, not a probability of a disaster unless explicitly identified as a model probability. The current saved prediction record does not retain model provenance, so historical records cannot reliably be attributed to a trained model."),
)


def _matches(question: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in question for phrase in phrases)


def _response(category: str, answer: str) -> dict[str, str]:
    return {
        "category": category,
        "answer": answer,
        "disclaimer": ASSISTANT_DISCLAIMER,
    }


def _latest_user_record(db: Session, model: Any, user_id: int) -> Any | None:
    return db.scalars(
        select(model).where(model.user_id == user_id).order_by(model.created_at.desc()).limit(1)
    ).first()


def _format_live(question: str, db: Session, user: User) -> str:
    if _matches(question, ("weather", "rainfall", "rain", "temperature", "wind")):
        observation = db.scalars(
            select(WeatherObservation).order_by(
                WeatherObservation.observation_time.desc(), WeatherObservation.id.desc()
            ).limit(1)
        ).first()
        if observation is None:
            return "No weather observation is currently stored in the database, so I cannot report a live weather value."
        values = (
            ("temperature", observation.temperature_c, "°C"),
            ("rain", observation.rain_mm, "mm"),
            ("precipitation", observation.precipitation_mm, "mm"),
            ("humidity", observation.humidity_percent, "%"),
            ("wind", observation.wind_speed_kmh, "km/h"),
            ("pressure", observation.pressure_hpa, "hPa"),
        )
        measurements = ", ".join(
            f"{name} {value:g} {unit}" for name, value, unit in values if value is not None
        )
        return (
            f"Latest stored weather for {observation.station_name} ({observation.source}): "
            f"{measurements or 'no measurement values recorded'}. "
            f"Observation time: {observation.observation_time.isoformat()}; fetched at: "
            f"{observation.fetched_at.isoformat()}. These are stored observations, not a forecast."
        )

    if _matches(question, ("hydrology", "river", "water level", "discharge", "cwc")):
        status = get_hydrology_status(db)
        source_details = []
        for source in status["sources"]:
            detail = f"{source['source']}: {source['status']}"
            if source.get("last_observation"):
                detail += f", observation {source['last_observation']}"
            if source.get("latest_station"):
                detail += f", station {source['latest_station']}"
            if source.get("water_level") is not None:
                detail += f", water level {source['water_level']} m"
            if source.get("rainfall") is not None:
                detail += f", rainfall {source['rainfall']} mm"
            source_details.append(detail)
        details = "; ".join(source_details) or "no configured source details"
        return f"Hydrology readiness is {status['status']}: {status['message']} {details}"

    if _matches(question, ("prediction", "risk score", "current risk", "risk estimate")):
        prediction = _latest_user_record(db, Prediction, user.id)
        if prediction is None:
            return "There is no saved prediction for your account, so I cannot report a current prediction."
        return (
            f"Your latest saved {prediction.disaster_type} estimate is {prediction.risk_score:g}/100 "
            f"({prediction.risk_level}), recorded {prediction.created_at.isoformat()} at "
            f"{prediction.latitude:g}, {prediction.longitude:g}. This database record does not retain "
            "the inference source or model version, so I cannot verify whether it came from the trained model."
        )

    if _matches(question, ("alert", "warning")):
        alert = _latest_user_record(db, Alert, user.id)
        if alert is None:
            return "There are no saved alerts for your account. This does not mean that no hazard exists; check official local alerts."
        return (
            f"Latest saved application alert: {alert.title} ({alert.severity}, {alert.disaster_type}), "
            f"created {alert.created_at.isoformat()}. DisasterGuard alerts are not official government warnings."
        )

    if _matches(question, ("simulation", "digital twin", "scenario")):
        simulation = _latest_user_record(db, Simulation, user.id)
        if simulation is None:
            return "There is no saved simulation for your account. DisasterGuard scenarios are heuristic what-if estimates, not physical forecasts."
        return (
            f"Latest saved what-if scenario: {simulation.scenario} ({simulation.disaster_type}), "
            f"created {simulation.created_at.isoformat()}. Results: {simulation.results}. "
            "This is a scenario estimate, not an actual prediction."
        )

    if _matches(question, ("resource", "inventory", "stock")):
        resources = list(db.scalars(select(Resource).order_by(Resource.name)).all())
        if not resources:
            return "No resource inventory is currently recorded in the database."
        available = [item for item in resources if item.status.casefold() == "available"]
        totals: dict[str, int] = {}
        for item in available:
            totals[item.resource_type] = totals.get(item.resource_type, 0) + item.quantity
        summary = ", ".join(f"{kind}: {quantity}" for kind, quantity in sorted(totals.items()))
        return f"Database inventory marked available: {summary or 'none'}. This is recorded inventory, not a guarantee of operational availability."

    readiness = get_data_readiness(db, user)
    components = [
        ("Weather", readiness["sources"]["weather"]),
        ("Hydrology", readiness["sources"]["hydrology"]),
        ("GIS", readiness["sources"]["gis"]),
        ("ML model", readiness["ml_model"]),
        ("Features", readiness["features"]),
        ("Prediction", readiness["prediction"]),
    ]
    statuses = "; ".join(f"{label}: {item['status']}" for label, item in components)
    if _matches(question, ("shap", "explanation")):
        if readiness["ml_model"]["status"] != "READY":
            return "SHAP explanation unavailable because the trained model is not ready. " + statuses
        return (
            f"{statuses}. SHAP values are only returned by inference when a compatible trained model "
            "is available; past predictions do not store SHAP contributions."
        )
    if _matches(question, ("model", "trained")):
        return f"{statuses}. {readiness['ml_model']['message']}"
    return f"Current component readiness: {statuses}. Checked at {readiness['checked_at']}."


def answer_question(question: str, db: Session, user: User) -> dict[str, str]:
    """Answer general/project questions or report read-only live system context."""
    normalized = re.sub(r"\s+", " ", question.strip().lower())
    if not normalized:
        raise ValueError("Enter a question.")

    if _matches(normalized, ("what is shap", "what does shap stand for")):
        return _response("general_knowledge", GENERAL_ANSWERS[7][1])

    live_query = _matches(normalized, ("latest", "current", "live", "right now", "today", "status", "how much"))
    if live_query:
        return _response("live_system_data", _format_live(normalized, db, user))

    for phrases, answer in PROJECT_ANSWERS:
        if _matches(normalized, phrases):
            if answer is not None:
                return _response("project_information", answer)
            return _response("live_system_data", _format_live(normalized, db, user))

    for phrases, answer in GENERAL_ANSWERS:
        if _matches(normalized, phrases):
            return _response("general_knowledge", answer)

    return _response(
        "general_knowledge",
        "I don't have a verified answer for that topic in my built-in disaster-management knowledge. "
        "You can ask about floods, cyclones, landslides, wildfires, preparedness, GIS, Digital Twins, "
        "SHAP, machine learning, or this project's live data and readiness.",
    )
