from typing import Literal
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from app.models.user import User
from app.schemas.earthquake_events import EarthquakeEventQueryResponse
from app.services.earthquake_event_service import query_earthquake_events
from app.services.usgs_comcat_client import (
    UsgsComcatRateLimitError,
    UsgsComcatResponseError,
    UsgsComcatTimeoutError,
    UsgsComcatUnavailableError,
)
from app.utils.authentication import get_current_user

router = APIRouter(prefix="/earthquake-events", tags=["USGS earthquake events"])


@router.get(
    "",
    response_model=EarthquakeEventQueryResponse,
    summary="Query bounded USGS ComCat earthquake events",
    description=(
        "Performs an authenticated, on-demand GeoJSON query. Results are source earthquake events, "
        "not predictions, warnings, damage assessments, or community reports."
    ),
)
def get_earthquake_events(
    west: float = Query(..., ge=-180, le=180),
    south: float = Query(..., ge=-90, le=90),
    east: float = Query(..., ge=-180, le=180),
    north: float = Query(..., ge=-90, le=90),
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
    min_magnitude: float | None = Query(default=None, ge=-10, le=10),
    max_magnitude: float | None = Query(default=None, ge=-10, le=10),
    review_status: Literal["automatic", "reviewed"] | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    _user: User = Depends(get_current_user),
) -> EarthquakeEventQueryResponse:
    try:
        return query_earthquake_events(
            west=west,
            south=south,
            east=east,
            north=north,
            start_time=start_time,
            end_time=end_time,
            min_magnitude=min_magnitude,
            max_magnitude=max_magnitude,
            review_status=review_status,
            limit=limit,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except UsgsComcatTimeoutError as error:
        raise HTTPException(status_code=504, detail="The USGS query timed out.") from error
    except UsgsComcatRateLimitError as error:
        headers = (
            {"Retry-After": str(error.retry_after_seconds)}
            if error.retry_after_seconds is not None
            else None
        )
        raise HTTPException(
            status_code=503,
            detail="The USGS service rate limit was reached.",
            headers=headers,
        ) from error
    except UsgsComcatUnavailableError as error:
        raise HTTPException(status_code=503, detail="The USGS service is temporarily unavailable.") from error
    except UsgsComcatResponseError as error:
        raise HTTPException(status_code=502, detail="The USGS service returned an invalid response.") from error
