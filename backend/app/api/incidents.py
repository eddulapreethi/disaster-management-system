from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.models.user import User
from app.schemas.incident import (
    HazardCategory,
    IncidentAnalyticsRead,
    IncidentCreate,
    IncidentDetailRead,
    IncidentListRead,
    IncidentReviewCreate,
    IncidentUpdate,
)
from app.services.incident_service import (
    create_incident,
    get_incident_detail,
    incident_analytics,
    list_incidents,
    review_incident,
    update_incident,
)
from app.utils.authentication import get_current_user

router = APIRouter(prefix="/incidents", tags=["community incident reports"])


def _require_aware(value: datetime | None, name: str) -> None:
    if value is not None and (value.tzinfo is None or value.utcoffset() is None):
        raise HTTPException(status_code=422, detail=f"{name} must include a timezone offset.")


@router.post("", response_model=IncidentDetailRead, status_code=status.HTTP_201_CREATED)
def submit_incident(
    data: IncidentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> IncidentDetailRead:
    return create_incident(db, user, data)


@router.get("", response_model=IncidentListRead)
def get_incidents(
    hazard_category: HazardCategory | None = Query(default=None),
    verification_status: str | None = Query(
        default=None,
        pattern="^(pending|verified|rejected|needs_review)$",
    ),
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
    west: float | None = Query(default=None, ge=-180, le=180),
    south: float | None = Query(default=None, ge=-90, le=90),
    east: float | None = Query(default=None, ge=-180, le=180),
    north: float | None = Query(default=None, ge=-90, le=90),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0, le=10000),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> IncidentListRead:
    _require_aware(start_time, "start_time")
    _require_aware(end_time, "end_time")
    if start_time and end_time and start_time > end_time:
        raise HTTPException(status_code=422, detail="start_time must not be after end_time.")

    bounds = (west, south, east, north)
    if all(value is None for value in bounds):
        bbox = None
    elif any(value is None for value in bounds):
        raise HTTPException(status_code=422, detail="Provide all four geographic bounds.")
    elif south > north:
        raise HTTPException(status_code=422, detail="south must not be greater than north.")
    else:
        bbox = (west, south, east, north)

    return list_incidents(
        db,
        user,
        hazard_category=hazard_category,
        status=verification_status,
        start_time=start_time,
        end_time=end_time,
        bbox=bbox,
        limit=limit,
        offset=offset,
    )


@router.get("/analytics", response_model=IncidentAnalyticsRead)
def get_incident_analytics(
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
    hazard_category: HazardCategory | None = Query(default=None),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> IncidentAnalyticsRead:
    _require_aware(start_time, "start_time")
    _require_aware(end_time, "end_time")
    if start_time and end_time and start_time > end_time:
        raise HTTPException(status_code=422, detail="start_time must not be after end_time.")
    return incident_analytics(
        db,
        start_time=start_time,
        end_time=end_time,
        hazard_category=hazard_category,
    )


@router.get("/{incident_id}", response_model=IncidentDetailRead)
def get_incident(
    incident_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> IncidentDetailRead:
    try:
        return get_incident_detail(db, user, incident_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.patch("/{incident_id}", response_model=IncidentDetailRead)
def edit_incident(
    incident_id: int,
    data: IncidentUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> IncidentDetailRead:
    try:
        return update_incident(db, user, incident_id, data)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/{incident_id}/reviews", response_model=IncidentDetailRead)
def review_incident_report(
    incident_id: int,
    data: IncidentReviewCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> IncidentDetailRead:
    try:
        return review_incident(db, user, incident_id, data)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
