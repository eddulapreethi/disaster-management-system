from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, computed_field, field_serializer

from app.models.user import User
from app.schemas.canonical_environmental import CanonicalEnvironmentalRecord
from app.schemas.provider import (
    ProviderLocation,
    ProviderProvenance,
    coverage_status_from_freshness,
)
from app.services.environmental_normalization_service import normalize_weather_record
from app.services.weather_service import (
    fetch_location_weather,
    get_collector_status,
    get_max_age_seconds,
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
    provider_metadata: dict[str, Any] | None = None

    @field_serializer("observation_time", "fetched_at", "created_at", when_used="json")
    def serialize_utc_timestamp(self, value: datetime) -> str:
        return utc_isoformat(value) or ""

    def _observation_age_seconds(self) -> float:
        observed_at = self.observation_time
        if observed_at.tzinfo is None:
            observed_at = observed_at.replace(tzinfo=timezone.utc)
        else:
            observed_at = observed_at.astimezone(timezone.utc)
        return (datetime.now(timezone.utc) - observed_at).total_seconds()

    @computed_field
    @property
    def freshness_status(self) -> str:
        age_seconds = self._observation_age_seconds()
        if age_seconds < -300:
            return "ERROR"
        if age_seconds > get_max_age_seconds():
            return "STALE"
        return "READY"

    @computed_field
    @property
    def coverage_status(self) -> str:
        return coverage_status_from_freshness(self.freshness_status)

    @computed_field
    @property
    def observation_age_seconds(self) -> int:
        return max(0, int(self._observation_age_seconds()))

    @computed_field
    @property
    def measurement_status(self) -> str:
        required = (self.temperature_c, self.precipitation_mm, self.wind_speed_kmh)
        return "UNAVAILABLE" if any(value is None for value in required) else "READY"

    @computed_field
    @property
    def measurement_units(self) -> dict[str, str]:
        return {
            "temperature_c": "°C",
            "humidity_percent": "%",
            "precipitation_mm": "mm",
            "rain_mm": "mm",
            "wind_speed_kmh": "km/h",
            "pressure_hpa": "hPa",
        }

    @computed_field
    @property
    def provenance(self) -> ProviderProvenance:
        return ProviderProvenance(
            provider="Open-Meteo",
            product="Stored current weather point observation",
            source_record_id=None,
            location=ProviderLocation(
                name=self.station_name,
                latitude=self.latitude,
                longitude=self.longitude,
                station_id=self.station_id,
                station_id_is_internal=True,
            ),
            observation_time=self.observation_time,
            fetched_at=self.fetched_at,
            units=self.measurement_units,
            freshness_status=self.freshness_status,
            provider_metadata={
                "stored_observation_id": self.id,
                "provider_specific_metadata_persisted": self.provider_metadata is not None,
                "source_metadata": self.provider_metadata or {},
            },
        )

    @computed_field
    @property
    def canonical_record(self) -> CanonicalEnvironmentalRecord:
        return normalize_weather_record(
            {
                "id": self.id,
                "provider": "Open-Meteo",
                "station_id": self.station_id,
                "station_name": self.station_name,
                "latitude": self.latitude,
                "longitude": self.longitude,
                "temperature_c": self.temperature_c,
                "humidity_percent": self.humidity_percent,
                "precipitation_mm": self.precipitation_mm,
                "rain_mm": self.rain_mm,
                "wind_speed_kmh": self.wind_speed_kmh,
                "pressure_hpa": self.pressure_hpa,
                "observation_time": self.observation_time,
                "fetched_at": self.fetched_at,
                "created_at": self.created_at,
                "provider_metadata": self.provider_metadata or {},
                "freshness_status": self.freshness_status,
                "quality_status": (
                    "PARTIAL"
                    if any(
                        value is None
                        for value in (self.temperature_c, self.precipitation_mm, self.wind_speed_kmh)
                    )
                    else "VALIDATED_SHAPE"
                ),
                "validation_findings": [],
                "values": {
                    "temperature_c": self.temperature_c,
                    "humidity_percent": self.humidity_percent,
                    "precipitation_mm": self.precipitation_mm,
                    "rain_mm": self.rain_mm,
                    "wind_speed_kmh": self.wind_speed_kmh,
                    "pressure_hpa": self.pressure_hpa,
                },
                "units": self.measurement_units,
            }
        )


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
