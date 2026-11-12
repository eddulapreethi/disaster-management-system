from fastapi import APIRouter, Depends, HTTPException, Query

from app.models.user import User
from app.schemas.provider import LocationCoverageResponse
from app.services.coverage_service import build_location_coverage
from app.utils.authentication import get_current_user

router = APIRouter(prefix="/coverage", tags=["provider coverage"])


@router.get(
    "",
    response_model=LocationCoverageResponse,
    summary="Report configured source scope for a coordinate",
    description=(
        "Accepts a WGS 84 point and reports configured source scope. It does not query upstream coverage "
        "catalogs or establish global provider availability."
    ),
)
def location_coverage(
    latitude: float = Query(ge=-90, le=90, allow_inf_nan=False),
    longitude: float = Query(ge=-180, le=180, allow_inf_nan=False),
    _user: User = Depends(get_current_user),
) -> LocationCoverageResponse:
    try:
        return build_location_coverage(latitude, longitude)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
