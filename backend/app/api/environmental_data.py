from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.models.user import User
from app.schemas.environmental_data import EnvironmentalDataResponse
from app.services.environmental_data_service import query_environmental_data
from app.utils.authentication import get_current_user

router = APIRouter(prefix="/environmental-data", tags=["environmental data"])


@router.get(
    "",
    response_model=EnvironmentalDataResponse,
    summary="Query stored environmental records",
    description=(
        "Queries stored weather and regional hydrology records. Counts and source statuses describe only "
        "the returned page; this endpoint does not check upstream provider coverage or determine whether "
        "a hazard is present or absent. Empty, stale, partial, unavailable, and unverified data are distinct."
    ),
)
def environmental_data(
    category: str | None = Query(default=None),
    provider: str | None = Query(default=None, min_length=1, max_length=120),
    west: float | None = Query(default=None, ge=-180, le=180),
    south: float | None = Query(default=None, ge=-90, le=90),
    east: float | None = Query(default=None, ge=-180, le=180),
    north: float | None = Query(default=None, ge=-90, le=90),
    latitude: float | None = Query(default=None, ge=-90, le=90),
    longitude: float | None = Query(default=None, ge=-180, le=180),
    radius_km: float = Query(default=25, gt=0, le=500),
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0, le=10000),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> EnvironmentalDataResponse:
    bbox_values = (west, south, east, north)
    if all(value is None for value in bbox_values):
        bbox = None
    elif any(value is None for value in bbox_values):
        raise HTTPException(status_code=422, detail="Provide all four geographic bounds.")
    else:
        bbox = (west, south, east, north)

    if (latitude is None) != (longitude is None):
        raise HTTPException(status_code=422, detail="Provide both latitude and longitude for a location filter.")

    try:
        return query_environmental_data(
            db,
            category=category,
            provider=provider,
            bbox=bbox,
            location=(latitude, longitude, radius_km) if latitude is not None else None,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=offset,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
