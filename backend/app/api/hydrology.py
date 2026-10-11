from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, computed_field, field_serializer
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.models.user import User
from app.schemas.hydrology import HydrologyStatusResponse
from app.services.data_readiness_service import get_hydrology_status
from app.services.hydrology_service import get_latest_observations, get_observations, get_stations
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
    water_level: float | None
    discharge: float | None
    rainfall: float | None
    observation_time: datetime
    fetched_at: datetime

    @field_serializer("observation_time", "fetched_at", when_used="json")
    def serialize_utc_timestamp(self, value: datetime) -> str:
        return utc_isoformat(value) or ""

    @computed_field
    @property
    def measurement_units(self) -> dict[str, str]:
        return {"water_level": "m", "rainfall": "mm"}


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
