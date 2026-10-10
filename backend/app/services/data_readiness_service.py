from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sys
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.hydrological_observation import HydrologicalObservation
from app.models.hydrology_collection_state import HydrologyCollectionState
from app.models.prediction import Prediction
from app.models.user import User
from app.services.hydrology_service import (
    configured_resources,
    get_latest_observations as get_latest_hydrology_observations,
    get_stale_after_hours,
)
from app.services.weather_service import get_weather_status

def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _source_readiness(
    source: str,
    resource_id: str,
    state: HydrologyCollectionState | None,
    latest: HydrologicalObservation | None,
    now: datetime,
    stale_after: timedelta,
) -> dict[str, Any]:
    last_fetch = state.last_successful_fetch_at if state else None
    if latest is None:
        status = "ERROR" if state and state.status == "ERROR" else "UNAVAILABLE"
        message = state.message if state and state.message else "No observation has been collected from this source yet."
    elif state and state.status == "ERROR":
        status = "ERROR"
        message = state.message or "The last collection attempt failed."
    elif now - _as_utc(latest.observation_time) > stale_after:
        status = "STALE"
        message = f"Latest source observation is older than {stale_after.total_seconds() / 3600:g} hours."
    else:
        status = "READY"
        message = "Latest observation is within the configured freshness window."
    return {
        "source": source,
        "resource_id": resource_id,
        "status": status,
        "message": message,
        "last_observation": latest.observation_time.isoformat() if latest else None,
        "last_fetch": last_fetch.isoformat() if last_fetch else None,
        "latest_station": latest.station_name if latest else None,
        "water_level": latest.water_level if latest else None,
        "discharge": latest.discharge if latest else None,
        "rainfall": latest.rainfall if latest else None,
        "records_received": state.records_received if state else 0,
        "inserted_count": state.inserted_count if state else 0,
        "duplicates_skipped": state.duplicates_skipped if state else 0,
        "parse_errors": state.parse_errors if state else 0,
    }


def get_hydrology_status(db: Session) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    stale_after = timedelta(hours=get_stale_after_hours())
    resources = configured_resources()
    states = {
        state.source: state
        for state in db.scalars(select(HydrologyCollectionState)).all()
    }
    observations = get_latest_hydrology_observations(db, limit=10000)
    latest_by_source: dict[str, HydrologicalObservation] = {}
    for observation in observations:
        latest_by_source.setdefault(observation.source, observation)
    source_statuses = [
        _source_readiness(
            source=f"nwdp:{resource['key']}",
            resource_id=resource["resource_id"],
            state=states.get(f"nwdp:{resource['key']}"),
            latest=latest_by_source.get(f"nwdp:{resource['key']}"),
            now=now,
            stale_after=stale_after,
        )
        for resource in resources
    ]
    statuses = {source["status"] for source in source_statuses}
    if "ERROR" in statuses:
        overall = "ERROR"
    elif "UNAVAILABLE" in statuses:
        overall = "UNAVAILABLE"
    elif "STALE" in statuses:
        overall = "STALE"
    else:
        overall = "READY"
    latest_candidates = [source["last_observation"] for source in source_statuses if source["last_observation"]]
    fetch_candidates = [source["last_fetch"] for source in source_statuses if source["last_fetch"]]
    message_by_status = {
        "READY": "All configured CWC sources have observations within the freshness window.",
        "STALE": "One or more CWC sources have stale observations.",
        "UNAVAILABLE": "One or more CWC sources have no collected observations.",
        "ERROR": "One or more CWC sources encountered a collection or parsing error.",
    }
    return {
        "source": "NWDP/NWIC CWC telemetry",
        "status": overall,
        "message": message_by_status[overall],
        "poll_interval_seconds": int(os.getenv("HYDROLOGY_POLL_INTERVAL_SECONDS", "60")),
        "stale_after_hours": int(stale_after.total_seconds() / 3600),
        "last_observation": max(latest_candidates) if latest_candidates else None,
        "last_fetch": max(fetch_candidates) if fetch_candidates else None,
        "sources": source_statuses,
    }


def _weather_status() -> dict[str, Any]:
    weather = get_weather_status()
    collector = weather["collector"]
    return {
        **{key: value for key, value in weather.items() if key != "collector"},
        "last_fetch": weather["last_successful_fetch"],
        "successful_locations": collector.get("successful_locations", 0),
        "configured_locations": collector.get("configured_locations", 0),
    }


def _get_ml_readiness(
    model_path: Path,
) -> tuple[
    dict[str, Any],
    tuple[str, ...],
    tuple[dict[str, str | float], ...],
    str,
    bool,
]:
    project_root = str(Path(__file__).resolve().parents[3])
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    from ml.prediction.predict import get_model_readiness
    from ml.preprocessing.feature_engineering import (
        FLOOD_FEATURES,
        FLOOD_FEATURE_SCHEMA,
        FLOOD_FEATURE_SCHEMA_VERSION,
    )
    from ml.preprocessing import feature_engineering

    return (
        get_model_readiness(model_path),
        FLOOD_FEATURES,
        FLOOD_FEATURE_SCHEMA,
        FLOOD_FEATURE_SCHEMA_VERSION,
        callable(getattr(feature_engineering, "build_inference_features", None)),
    )


def get_data_readiness(db: Session, user: User) -> dict[str, Any]:
    """Report evidence-based readiness without initiating automatic predictions."""
    weather = _weather_status()
    hydrology = get_hydrology_status(db)
    has_prediction_location = db.scalar(
        select(Prediction.id).where(Prediction.user_id == user.id).limit(1)
    ) is not None
    gis = {
        "status": "READY" if has_prediction_location else "UNAVAILABLE",
        "message": "Saved prediction coordinates are available for the account risk map."
        if has_prediction_location
        else "No saved prediction coordinates are available to map.",
    }

    default_model = (
        Path(__file__).resolve().parents[3]
        / "ml"
        / "models"
        / "trained_models"
        / "flood_risk_model.joblib"
    )
    model_path = Path(os.getenv("DISASTERGUARD_MODEL_PATH", str(default_model)))
    (
        model,
        flood_features,
        feature_schema,
        feature_schema_version,
        runtime_feature_builder_ready,
    ) = _get_ml_readiness(model_path)
    canonical_schema_valid = (
        feature_schema_version == "flood-risk-factors-v1"
        and len(flood_features) == 20
        and len(set(flood_features)) == len(flood_features)
        and [item["name"] for item in feature_schema] == list(flood_features)
    )
    feature_schema_verified = (
        canonical_schema_valid
        and model.get("feature_schema_verified") is True
    )
    features = {
        "status": "READY" if feature_schema_verified else "NOT_READY",
        "message": (
            "The ordered schema and value ranges passed validation, and a training manifest declares feature meanings, units, sources, and transformations."
            if feature_schema_verified
            else (
                "The current 20 named inputs are undocumented 0-16 indices with no authoritative units, "
                "source mapping, or validated dataset manifest. EM-DAT event/impact records cannot supply "
                "these environmental features."
            )
        ),
        "schema_version": feature_schema_version,
        "feature_count": len(flood_features),
    }
    prediction_reasons = []
    if model["status"] != "READY":
        prediction_reasons.append("a compatible trained model is not ready")
    if features["status"] != "READY":
        prediction_reasons.append("the feature definitions/data pipeline are not verified")
    if not runtime_feature_builder_ready:
        prediction_reasons.append(
            "the backend has no verified runtime feature builder for the current weather/hydrology sources"
        )
    prediction_ready = not prediction_reasons
    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "sources": {"weather": weather, "hydrology": hydrology, "gis": gis},
        "ml_model": model,
        "features": features,
        "prediction": {
            "status": "READY" if prediction_ready else "NOT_READY",
            "automatic_prediction_enabled": False,
            "message": (
                "User-initiated inference is available with the validated model and feature pipeline."
                if prediction_ready
                else "User-triggered ML inference is not ready: " + "; ".join(prediction_reasons) + "."
            ),
        },
    }
