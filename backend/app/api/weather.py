from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, field_serializer

from app.models.user import User
from app.services.weather_service import (
    fetch_location_weather,
    get_collector_status,
    get_latest_observations,
    get_weather_status,
)
from app.utils.authentication import get_current_user
from app.utils.utc_timestamps import utc_isoformat

router = APIRouter(prefix="/weather", tags=["weather"])


class WeatherObservationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    station_id: str
    station_name: str
    source: str
    latitude: float
    longitude: float
    temperature_c: float | None
    humidity_percent: float | None
    precipitation_mm: float | None
    rain_mm: float | None
    wind_speed_kmh: float | None
    pressure_hpa: float | None
    observation_time: datetime
    fetched_at: datetime
    created_at: datetime

    @field_serializer("observation_time", "fetched_at", "created_at", when_used="json")
    def serialize_utc_timestamp(self, value: datetime) -> str:
        return utc_isoformat(value) or ""


class WeatherSnapshot(BaseModel):
    collector: dict[str, Any]
    observations: list[WeatherObservationRead]


@router.get("/latest", response_model=WeatherSnapshot)
def latest_weather(_user: User = Depends(get_current_user)):
    return {
        "collector": get_collector_status(),
        "observations": get_latest_observations(),
    }


@router.get("/current")
def current_weather(
    latitude: float = Query(ge=-90, le=90, allow_inf_nan=False),
    longitude: float = Query(ge=-180, le=180, allow_inf_nan=False),
    _user: User = Depends(get_current_user),
):
    try:
        observation = fetch_location_weather(latitude, longitude)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    return observation


@router.get("/status")
def weather_status(_user: User = Depends(get_current_user)):
    return get_weather_status()
