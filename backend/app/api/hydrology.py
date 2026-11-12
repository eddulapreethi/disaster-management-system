from datetime import datetime, timezone
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, computed_field, field_serializer
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.models.user import User
from app.schemas.canonical_environmental import CanonicalEnvironmentalRecord
from app.schemas.hydrology import HydrologyStatusResponse
from app.schemas.provider import (
    ProviderLocation,
    ProviderProvenance,
    coverage_status_from_freshness,
)
from app.services.data_readiness_service import get_hydrology_status
from app.services.environmental_normalization_service import normalize_hydrology_record
from app.services.hydrology_service import (
    configured_resources,
    get_latest_observations,
    get_observations,
    get_stale_after_hours,
    get_stations,
)
from app.utils.authentication import get_current_user
from app.utils.utc_timestamps import utc_isoformat

router = APIRouter(prefix="/hydrology", tags=["hydrology"])


class HydrologicalObservationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source: str
    source_resource_id: str
    source_record_id: int
    station_id: str
    station_name: str
    river_name: str | None
    state_name: str | None
    district_name: str | None
    latitude: float | None
    longitude: float | None
    station_id_is_internal: bool = True
    water_level: float | None
    discharge: float | None
    rainfall: float | None
    observation_time: datetime
    fetched_at: datetime
    provider_metadata: dict[str, Any]

    @field_serializer("observation_time", "fetched_at", when_used="json")
    def serialize_utc_timestamp(self, value: datetime) -> str:
        return utc_isoformat(value) or ""

    @computed_field
    @property
    def measurement_units(self) -> dict[str, str]:
        return {"water_level": "m", "rainfall": "mm"}

    def _freshness_status(self) -> str:
        observed_at = self.observation_time
        if observed_at.tzinfo is None:
            observed_at = observed_at.replace(tzinfo=timezone.utc)
        else:
            observed_at = observed_at.astimezone(timezone.utc)
        age_seconds = (datetime.now(timezone.utc) - observed_at).total_seconds()
        if age_seconds < -300:
            return "ERROR"
        resource = next(
            (item for item in configured_resources() if item["resource_id"] == self.source_resource_id),
            None,
        )
        stale_after_seconds = get_stale_after_hours(resource) * 3600
        return "STALE" if age_seconds > stale_after_seconds else "READY"

    @computed_field
    @property
    def coverage_status(self) -> str:
        return coverage_status_from_freshness(self._freshness_status())

    @computed_field
    @property
    def provenance(self) -> ProviderProvenance:
        return ProviderProvenance(
            provider="NWDP/NWIC CWC",
            product=self.source_resource_id,
            source_record_id=self.source_record_id,
            location=ProviderLocation(
                name=self.station_name,
                latitude=self.latitude,
                longitude=self.longitude,
                station_id=self.station_id,
                station_id_is_internal=True,
                region=self.state_name,
            ),
            observation_time=self.observation_time,
            fetched_at=self.fetched_at,
            units=self.measurement_units,
            freshness_status=self._freshness_status(),
            provider_metadata={
                "source": self.source,
                "source_resource_id": self.source_resource_id,
                "station_id_is_internal": True,
                "river_name": self.river_name,
                "state_name": self.state_name,
                "district_name": self.district_name,
                "measurement_metadata_status": "UNVERIFIED",
                "source_metadata": self.provider_metadata,
            },
        )

    @computed_field
    @property
    def canonical_record(self) -> CanonicalEnvironmentalRecord:
        return normalize_hydrology_record(
            {
                "provider": "NWDP/NWIC CWC",
                "source": self.source,
                "source_resource_id": self.source_resource_id,
                "source_record_id": self.source_record_id,
                "station_id": self.station_id,
                "station_name": self.station_name,
                "river_name": self.river_name,
                "state_name": self.state_name,
                "district_name": self.district_name,
                "latitude": self.latitude,
                "longitude": self.longitude,
                "water_level": self.water_level,
                "discharge": self.discharge,
                "rainfall": self.rainfall,
                "observation_time": self.observation_time,
                "fetched_at": self.fetched_at,
                "provider_metadata": self.provider_metadata,
                "quality_status": "UNVERIFIED",
                "freshness_status": self._freshness_status(),
                "validation_findings": [],
                "values": {
                    "water_level": self.water_level,
                    "discharge": self.discharge,
                    "rainfall": self.rainfall,
                },
            }
        )


@router.get("/status", response_model=HydrologyStatusResponse)
def hydrology_status(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    try:
        return get_hydrology_status(db)
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.get("/latest", response_model=list[HydrologicalObservationRead])
def latest_observations(
    station_id: str | None = None,
    source: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return get_latest_observations(db, station_id=station_id, source=source, limit=limit)


@router.get("/stations")
def hydrology_stations(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return get_stations(db)


@router.get("/observations", response_model=list[HydrologicalObservationRead])
def hydrology_observations(
    station_id: str | None = None,
    source: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    limit: int = Query(default=500, ge=1, le=5000),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    if start_time and end_time and start_time > end_time:
        raise HTTPException(status_code=422, detail="start_time must be before end_time.")
    return get_observations(
        db,
        station_id=station_id,
        source=source,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
    )
