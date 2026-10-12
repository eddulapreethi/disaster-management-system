from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import os
from pathlib import Path
import sys
import threading
import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.hydrological_observation import HydrologicalObservation
from app.models.hydrology_collection_state import HydrologyCollectionState
from app.models.prediction import Prediction
from app.models.user import User
from app.services.hydrology_service import (
    configured_resources,
    get_poll_interval_seconds as get_hydrology_poll_interval_seconds,
    get_latest_observations as get_latest_hydrology_observations,
    get_stale_after_hours,
)
from app.services.gis_readiness_service import get_gis_data_readiness
from app.services.historical_data_readiness import get_historical_data_readiness
from app.services.weather_service import get_weather_status
from app.utils.utc_timestamps import utc_isoformat

def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _source_readiness(
    source: str,
    resource_id: str,
    update_frequency: str,
    stale_after: timedelta,
    state: HydrologyCollectionState | None,
    latest: HydrologicalObservation | None,
    now: datetime,
) -> dict[str, Any]:
    last_fetch = state.last_successful_fetch_at if state else None
    observation_age_seconds = (
        (now - _as_utc(latest.observation_time)).total_seconds()
        if latest
        else None
    )
    if latest is None:
        freshness_status = "UNAVAILABLE"
        status = "ERROR" if state and state.status == "ERROR" else "UNAVAILABLE"
        message = state.message if state and state.message else "No observation has been collected from this source yet."
    elif observation_age_seconds is not None and observation_age_seconds < -300:
        freshness_status = "ERROR"
        status = "ERROR"
        message = "The latest observation timestamp is more than five minutes in the future."
    elif observation_age_seconds is not None and observation_age_seconds > stale_after.total_seconds():
        freshness_status = "STALE"
        status = "ERROR" if state and state.status == "ERROR" else "STALE"
        message = f"Latest source observation is older than {stale_after.total_seconds() / 3600:g} hours."
    else:
        freshness_status = "READY"
        status = "ERROR" if state and state.status == "ERROR" else "READY"
        message = "Latest observation is within the configured freshness window."
    if state is None or state.last_successful_fetch_at is None:
        collection_status = "UNAVAILABLE"
    elif state.status == "ERROR":
        collection_status = (
            "PARSE_ERRORS"
            if state.parse_errors
            else "ERROR"
        )
    elif state.records_returned == 0:
        collection_status = "SUCCESS_EMPTY_RESPONSE"
    elif state.records_received == 0:
        collection_status = "SUCCESS_NO_NEW_DATA"
    elif state.inserted_count == 0 and state.duplicates_skipped:
        collection_status = "SUCCESS_DUPLICATES_ONLY"
    elif state.inserted_count:
        collection_status = "SUCCESS_WITH_NEW_DATA"
    else:
        collection_status = "SUCCESS_NO_NEW_DATA"
    return {
        "source": source,
        "resource_id": resource_id,
        "status": status,
        "freshness_status": freshness_status,
        "collection_status": collection_status,
        "message": message,
        "last_observation": utc_isoformat(latest.observation_time) if latest else None,
        "observation_age_seconds": max(0, int(observation_age_seconds)) if observation_age_seconds is not None else None,
        "last_fetch": utc_isoformat(last_fetch),
        "station_id": latest.station_id if latest else None,
        "latest_station": latest.station_name if latest else None,
        "update_frequency": update_frequency,
        "stale_after_hours": int(stale_after.total_seconds() / 3600),
        "water_level": latest.water_level if latest else None,
        "water_level_unit": "m" if latest and latest.water_level is not None else None,
        "discharge": latest.discharge if latest else None,
        "rainfall": latest.rainfall if latest else None,
        "rainfall_unit": "mm" if latest and latest.rainfall is not None else None,
        "records_received": state.records_received if state else 0,
        "records_returned": state.records_returned if state else 0,
        "valid_records": state.valid_records if state else 0,
        "inserted_count": state.inserted_count if state else 0,
        "duplicates_skipped": state.duplicates_skipped if state else 0,
        "parse_errors": state.parse_errors if state else 0,
        "newer_observation_found": state.newer_observation_found if state else False,
        "latest_error": state.last_error if state else None,
    }


def get_hydrology_status(db: Session) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
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
            update_frequency=resource["update_frequency"],
            stale_after=timedelta(hours=int(resource["stale_after_hours"])),
            state=states.get(f"nwdp:{resource['key']}"),
            latest=latest_by_source.get(f"nwdp:{resource['key']}"),
            now=now,
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
        "poll_interval_seconds": get_hydrology_poll_interval_seconds(),
        "stale_after_hours": get_stale_after_hours(),
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
    project_root_string = str(Path(__file__).resolve().parents[3])
    if project_root_string not in sys.path:
        sys.path.insert(0, project_root_string)
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


_READINESS_CACHE_TTL_SECONDS = 30.0
_READINESS_CACHE_LOCK = threading.RLock()
_READINESS_CACHE: dict[tuple[str, str, str], tuple[float, dict[str, Any]]] = {}


def _readiness_fingerprint(project_root: Path, model_path: Path, user_id: int) -> str:
    root = project_root.resolve()
    digest = hashlib.sha256()
    key_candidates = [
        root / "ml" / "datasets" / "historical_data" / "processed",
        root / "ml" / "datasets" / "historical_disasters" / "EM-DAT",
        root / "ml" / "models" / "trained_models",
    ]
    for location in key_candidates:
        if not location.exists():
            continue
        for path in sorted(location.rglob("*")):
            if path.is_file():
                stat = path.stat()
                digest.update(str(path.relative_to(root)).encode("utf-8"))
                digest.update(str(stat.st_size).encode("utf-8"))
                digest.update(str(stat.st_mtime_ns).encode("utf-8"))
    digest.update(f"model_path={model_path}\nuser_id={user_id}\n".encode("utf-8"))
    return digest.hexdigest()


def get_data_readiness(db: Session, user: User) -> dict[str, Any]:
    """Report evidence-based readiness without initiating automatic predictions."""
    project_root = Path(__file__).resolve().parents[3]
    default_model = project_root / "ml" / "models" / "trained_models" / "flood_risk_model.joblib"
    model_path = Path(os.getenv("DISASTERGUARD_MODEL_PATH", str(default_model)))
    cache_key = ("data_readiness", str(project_root), _readiness_fingerprint(project_root, model_path, user.id))
    now = time.monotonic()
    with _READINESS_CACHE_LOCK:
        cached = _READINESS_CACHE.get(cache_key)
        if cached and now - cached[0] < _READINESS_CACHE_TTL_SECONDS:
            return deepcopy(cached[1])

    weather = _weather_status()
    hydrology = get_hydrology_status(db)
    has_prediction_location = db.scalar(
        select(Prediction.id).where(Prediction.user_id == user.id).limit(1)
    ) is not None
    gis = get_gis_data_readiness(project_root)
    gis["saved_prediction_locations_available"] = has_prediction_location

    (
        model,
        _legacy_flood_features,
        _legacy_feature_schema,
        _legacy_feature_schema_version,
        runtime_feature_builder_ready,
    ) = _get_ml_readiness(model_path)
    from ml.preprocessing.flood_environmental_dataset import (
        FEATURE_SCHEMA as environmental_feature_schema,
        SCHEMA_VERSION as environmental_feature_schema_version,
        validate_feature_schema,
    )

    validate_feature_schema()
    features = {
        "status": "READY" if runtime_feature_builder_ready and model.get("status") == "READY" else "NOT_READY",
        "contract_status": "VALIDATED",
        "runtime_builder_status": "READY" if runtime_feature_builder_ready else "NOT_READY",
        "legacy_feature_schema_status": "RETIRED",
        "message": (
            f"The {environmental_feature_schema_version} environmental candidate contract declares "
            f"{len(environmental_feature_schema)} source-backed variables for historical analysis. "
            "No compatible model or live runtime feature builder is available. The legacy 20-index "
            "features are retired from active inference."
        ),
        "schema_version": environmental_feature_schema_version,
        "feature_count": len(environmental_feature_schema),
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
    result = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "sources": {"weather": weather, "hydrology": hydrology, "gis": gis},
        "historical_data": get_historical_data_readiness(project_root),
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
    with _READINESS_CACHE_LOCK:
        _READINESS_CACHE[cache_key] = (time.monotonic(), result)
    return deepcopy(result)
