from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from app.models.user import User
from app.services.weather_service import get_collector_status, get_latest_observations, get_weather_status
from app.utils.authentication import get_current_user

router = APIRouter(prefix="/weather", tags=["weather"])


class WeatherObservationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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


class WeatherSnapshot(BaseModel):
    collector: dict[str, Any]
    observations: list[WeatherObservationRead]


@router.get("/latest", response_model=WeatherSnapshot)
def latest_weather(_user: User = Depends(get_current_user)):
    return {
        "collector": get_collector_status(),
        "observations": get_latest_observations(),
    }


@router.get("/status")
def weather_status(_user: User = Depends(get_current_user)):
    return get_weather_status()
