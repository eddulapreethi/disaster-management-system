from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field

from app.models.user import User
from app.services import copernicus_service
from app.services.copernicus_service import CopernicusAPIError, CopernicusConfigurationError
from app.utils.authentication import get_current_user

router = APIRouter(prefix="/satellite", tags=["satellite"])


class SatelliteFeature(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str | None = None
    collection: str | None = None
    sensing_time: str | None = None
    cloud_coverage: float | None = None
    platform: str | None = None
    instruments: list[str] | None = None
    bbox: list[float] | None = None
    geometry: dict[str, Any] | None = None
    assets: dict[str, dict[str, Any]] = Field(default_factory=dict)


class SatelliteSearchResponse(BaseModel):
    collection: str
    features: list[SatelliteFeature]
    context: dict[str, Any]
    query: dict[str, Any]


def _raise_service_error(error: Exception) -> HTTPException:
    if isinstance(error, CopernicusConfigurationError):
        return HTTPException(status_code=503, detail=str(error))
    if isinstance(error, CopernicusAPIError):
        return HTTPException(status_code=502, detail=str(error))
    if isinstance(error, ValueError):
        return HTTPException(status_code=422, detail=str(error))
    return HTTPException(status_code=502, detail="Copernicus service request failed.")


def _bbox(
    west: float | None,
    south: float | None,
    east: float | None,
    north: float | None,
) -> tuple[float, float, float, float] | None:
    values = (west, south, east, north)
    if all(value is None for value in values):
        return None
    if any(value is None for value in values):
        raise HTTPException(status_code=422, detail="Provide all four bbox values: west, south, east and north.")
    return (west, south, east, north)


@router.get("/status")
def satellite_status(_user: User = Depends(get_current_user)) -> dict[str, Any]:
    """Verify backend OAuth and report service availability without exposing tokens."""
    try:
        copernicus_service.authenticate()
    except (CopernicusConfigurationError, CopernicusAPIError) as error:
        raise _raise_service_error(error) from None
    return {"service": "Copernicus", "authenticated": True, "sentinel1": True, "sentinel2": True}


@router.get("/search/sentinel-2", response_model=SatelliteSearchResponse)
def search_sentinel2(
    start_date: date,
    end_date: date,
    latitude: float | None = Query(default=None, ge=-90, le=90),
    longitude: float | None = Query(default=None, ge=-180, le=180),
    west: float | None = Query(default=None, ge=-180, le=180),
    south: float | None = Query(default=None, ge=-90, le=90),
    east: float | None = Query(default=None, ge=-180, le=180),
    north: float | None = Query(default=None, ge=-90, le=90),
    cloud_coverage: float | None = Query(default=None, ge=0, le=100),
    limit: int = Query(default=10, ge=1, le=100),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        return copernicus_service.search_sentinel2(
            start_date=start_date,
            end_date=end_date,
            latitude=latitude,
            longitude=longitude,
            bbox=_bbox(west, south, east, north),
            cloud_coverage=cloud_coverage,
            limit=limit,
        )
    except (CopernicusAPIError, CopernicusConfigurationError, ValueError) as error:
        raise _raise_service_error(error) from None


@router.get("/search/sentinel-1", response_model=SatelliteSearchResponse)
def search_sentinel1(
    start_date: date,
    end_date: date,
    latitude: float | None = Query(default=None, ge=-90, le=90),
    longitude: float | None = Query(default=None, ge=-180, le=180),
    west: float | None = Query(default=None, ge=-180, le=180),
    south: float | None = Query(default=None, ge=-90, le=90),
    east: float | None = Query(default=None, ge=-180, le=180),
    north: float | None = Query(default=None, ge=-90, le=90),
    limit: int = Query(default=10, ge=1, le=100),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        return copernicus_service.search_sentinel1(
            start_date=start_date,
            end_date=end_date,
            latitude=latitude,
            longitude=longitude,
            bbox=_bbox(west, south, east, north),
            limit=limit,
        )
    except (CopernicusAPIError, CopernicusConfigurationError, ValueError) as error:
        raise _raise_service_error(error) from None


@router.get("/image/{collection}")
def get_satellite_image(
    collection: Literal["sentinel-1", "sentinel-2"],
    start_date: date,
    end_date: date,
    latitude: float = Query(ge=-90, le=90),
    longitude: float = Query(ge=-180, le=180),
    cloud_coverage: float | None = Query(default=None, ge=0, le=100),
    width: int = Query(default=512, ge=1, le=1024),
    height: int = Query(default=512, ge=1, le=1024),
    _user: User = Depends(get_current_user),
) -> Response:
    """Stream a small Process API image for the AOI; never fetch a whole product."""
    try:
        content = copernicus_service.get_satellite_image(
            collection=collection,
            start_date=start_date,
            end_date=end_date,
            latitude=latitude,
            longitude=longitude,
            cloud_coverage=cloud_coverage,
            width=width,
            height=height,
        )
    except (CopernicusAPIError, CopernicusConfigurationError, ValueError) as error:
        raise _raise_service_error(error) from None
    return Response(
        content=content,
        media_type="image/tiff",
        headers={"Content-Disposition": "inline; filename=satellite-aoi.tiff"},
    )
