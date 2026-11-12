from datetime import date, datetime
import json
from typing import Any, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, field_serializer

from app.models.user import User
from app.schemas.canonical_environmental import CanonicalEnvironmentalRecord
from app.schemas.provider import ProviderLocation, ProviderProvenance
from app.services import copernicus_service
from app.services.copernicus_service import (
    CopernicusAPIError,
    CopernicusConfigurationError,
    CopernicusSceneNotFoundError,
    is_valid_geotiff,
)
from app.services.environmental_normalization_service import normalize_satellite_acquisition
from app.utils.authentication import get_current_user
from app.utils.utc_timestamps import utc_isoformat

router = APIRouter(prefix="/satellite", tags=["satellite"])


class SatelliteFeature(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str | None = None
    collection: str | None = None
    sensing_time: str | None = None
    acquisition_time: str | None = None
    cloud_coverage: float | None = None
    platform: str | None = None
    instruments: list[str] | None = None
    bbox: list[float] | None = None
    geometry: dict[str, Any] | None = None
    assets: dict[str, dict[str, Any]] = Field(default_factory=dict)
    provenance: ProviderProvenance | None = None
    canonical_record: CanonicalEnvironmentalRecord | None = None


class SatelliteSearchResponse(BaseModel):
    collection: str
    fetched_at: datetime
    features: list[SatelliteFeature]
    context: dict[str, Any]
    query: dict[str, Any]
    catalog_search_status: Literal["COMPLETED"]
    catalog_results_status: Literal["RESULTS_FOUND", "NO_RESULTS"]
    imagery_status: Literal["NOT_REQUESTED"]

    @field_serializer("fetched_at", when_used="json")
    def serialize_fetched_at(self, value: datetime) -> str:
        return utc_isoformat(value) or ""


class SatelliteServiceStatus(BaseModel):
    service: Literal["Copernicus"]
    authenticated: bool = Field(
        description="OAuth authentication succeeded; does not indicate Catalog or imagery availability."
    )
    authentication_status: Literal["AUTHENTICATED"]
    catalog_search_status: Literal["NOT_CHECKED"]
    catalog_results_status: Literal["NOT_CHECKED"]
    imagery_status: Literal["NOT_CHECKED"]
    details: str


def _satellite_search_response(
    result: dict[str, Any],
    *,
    latitude: float | None,
    longitude: float | None,
) -> dict[str, Any]:
    try:
        fetched_at = datetime.fromisoformat(str(result["fetched_at"]).replace("Z", "+00:00"))
        if fetched_at.tzinfo is None:
            raise ValueError("Catalog fetch timestamp must include a timezone.")
    except (KeyError, TypeError, ValueError) as error:
        raise CopernicusAPIError("Copernicus Catalog response is missing a valid fetch timestamp.") from error

    enriched_features = []
    requested_bbox = result.get("query", {}).get("bbox")
    for feature in result["features"]:
        acquisition_raw = feature.get("acquisition_time") or feature.get("sensing_time")
        try:
            acquisition_time = (
                datetime.fromisoformat(str(acquisition_raw).replace("Z", "+00:00"))
                if acquisition_raw
                else None
            )
        except ValueError:
            acquisition_time = None
        if acquisition_time is not None and acquisition_time.tzinfo is None:
            acquisition_time = acquisition_time.replace(tzinfo=fetched_at.tzinfo)

        canonical_record = normalize_satellite_acquisition(
            provider="Copernicus Data Space",
            collection=feature.get("collection") or result["collection"],
            catalog_item_id=feature.get("id"),
            acquisition_time=acquisition_time,
            retrieved_at=fetched_at,
            requested_bbox=requested_bbox,
            source_bbox=feature.get("bbox"),
            requested_point=(
                {"latitude": latitude, "longitude": longitude}
                if latitude is not None and longitude is not None
                else None
            ),
            source_metadata={
                "platform": feature.get("platform"),
                "instruments": feature.get("instruments"),
                "cloud_coverage": feature.get("cloud_coverage"),
            },
        )
        enriched_features.append(
            {
                **feature,
                "canonical_record": canonical_record,
                "provenance": ProviderProvenance(
                    provider="Copernicus Data Space",
                    product=feature.get("collection") or result["collection"],
                    source_record_id=feature.get("id"),
                    location=ProviderLocation(latitude=latitude, longitude=longitude),
                    observation_time=acquisition_time,
                    fetched_at=fetched_at,
                    units={"cloud_coverage": "%"} if feature.get("cloud_coverage") is not None else {},
                    freshness_status="UNVERIFIED",
                    provider_metadata={
                        "acquisition_time_raw": acquisition_raw,
                        "platform": feature.get("platform"),
                        "instruments": feature.get("instruments"),
                        "cloud_coverage": feature.get("cloud_coverage"),
                        "bbox": feature.get("bbox"),
                    },
                ),
            }
        )
    return {
        **result,
        "features": enriched_features,
        "catalog_search_status": "COMPLETED",
        "catalog_results_status": "RESULTS_FOUND" if enriched_features else "NO_RESULTS",
        "imagery_status": "NOT_REQUESTED",
    }


def _raise_service_error(error: Exception) -> HTTPException:
    if isinstance(error, CopernicusConfigurationError):
        return HTTPException(status_code=503, detail=str(error))
    if isinstance(error, CopernicusSceneNotFoundError):
        return HTTPException(status_code=404, detail=str(error))
    if isinstance(error, CopernicusAPIError):
        return HTTPException(status_code=502, detail=str(error))
    if isinstance(error, ValueError):
        return HTTPException(status_code=422, detail=str(error))
    return HTTPException(status_code=502, detail="Copernicus service request failed.")


@router.get(
    "/scene/sentinel-2",
    summary="Request a bounded Sentinel-2 image",
    description=(
        "Searches the Catalog and requests a bounded Process API image. A successful response proves image "
        "retrieval for this request only; Process output is not guaranteed to be pinned to the returned "
        "Catalog item. Acquisition and request/retrieval timestamps are distinct."
    ),
)
def retrieve_sentinel2_scene(
    start_date: date,
    end_date: date,
    latitude: float | None = Query(default=None, ge=-90, le=90),
    longitude: float | None = Query(default=None, ge=-180, le=180),
    west: float | None = Query(default=None, ge=-180, le=180),
    south: float | None = Query(default=None, ge=-90, le=90),
    east: float | None = Query(default=None, ge=-180, le=180),
    north: float | None = Query(default=None, ge=-90, le=90),
    cloud_coverage: float | None = Query(default=None, ge=0, le=100),
    width: int = Query(default=512, ge=1, le=1024),
    height: int = Query(default=512, ge=1, le=1024),
    _user: User = Depends(get_current_user),
) -> Response:
    """Return a bounded Sentinel-2 GeoTIFF plus encoded scene provenance headers."""
    bounds = _bbox(west, south, east, north)
    has_point = latitude is not None or longitude is not None
    has_complete_point = latitude is not None and longitude is not None
    if has_point != has_complete_point:
        raise HTTPException(status_code=422, detail="Provide both latitude and longitude for a point query.")
    if (bounds is None) == (not has_complete_point):
        raise HTTPException(status_code=422, detail="Provide either a complete point or all four bbox values, but not both.")

    try:
        result = copernicus_service.retrieve_sentinel2_scene(
            start_date=start_date,
            end_date=end_date,
            latitude=latitude,
            longitude=longitude,
            bbox=bounds,
            cloud_coverage=cloud_coverage,
            width=width,
            height=height,
        )
    except (CopernicusAPIError, CopernicusConfigurationError, ValueError) as error:
        raise _raise_service_error(error) from None
    if not is_valid_geotiff(result["image"], width=result["width"], height=result["height"]):
        raise HTTPException(status_code=502, detail="Copernicus Process API returned an invalid GeoTIFF image.")

    metadata = {
        **result["provenance"],
        "width": result["width"],
        "height": result["height"],
        "format": result["format"],
        "processing_parameters": result["processing_parameters"],
        "catalog_search_status": "COMPLETED",
        "catalog_results_status": "RESULTS_FOUND",
        "imagery_status": "RETRIEVED",
    }
    if result.get("canonical_record") is not None:
        metadata["canonical_record"] = result["canonical_record"]
    return Response(
        content=result["image"],
        media_type=result["format"],
        headers={
            "Content-Disposition": 'attachment; filename="sentinel-2-scene.tiff"',
            "X-Satellite-Metadata": quote(json.dumps(metadata, separators=(",", ":"), allow_nan=False)),
            "X-Catalog-Item-ID": quote(str(result["catalog_item_id"]), safe=""),
            "X-Acquisition-Time": result["provenance"]["acquisition_time"],
            "X-Catalog-Fetched-At": result["provenance"]["catalog_fetched_at"],
            "X-Process-Requested-At": result["provenance"]["process_requested_at"],
            "X-Download-Time": result["provenance"]["downloaded_at"],
            "X-Scene-Match-Status": result["provenance"]["scene_match_status"],
        },
    )


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


@router.get(
    "/status",
    response_model=SatelliteServiceStatus,
    summary="Check Copernicus authentication only",
    description=(
        "Tests OAuth authentication. Catalog search and scene results are not checked, and no imagery "
        "is requested by this endpoint."
    ),
)
def satellite_status(_user: User = Depends(get_current_user)) -> SatelliteServiceStatus:
    try:
        copernicus_service.authenticate()
    except (CopernicusConfigurationError, CopernicusAPIError) as error:
        raise _raise_service_error(error) from None
    return SatelliteServiceStatus(
        service="Copernicus",
        authenticated=True,
        authentication_status="AUTHENTICATED",
        catalog_search_status="NOT_CHECKED",
        catalog_results_status="NOT_CHECKED",
        imagery_status="NOT_CHECKED",
        details="OAuth succeeded; Catalog availability, scene results, and image retrieval were not checked.",
    )


@router.get(
    "/search/sentinel-2",
    response_model=SatelliteSearchResponse,
    summary="Search the Sentinel-2 Catalog",
    description="Returns request-time Catalog metadata only; it does not request or verify imagery.",
)
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
        return _satellite_search_response(
            copernicus_service.search_sentinel2(
                start_date=start_date,
                end_date=end_date,
                latitude=latitude,
                longitude=longitude,
                bbox=_bbox(west, south, east, north),
                cloud_coverage=cloud_coverage,
                limit=limit,
            ),
            latitude=latitude,
            longitude=longitude,
        )
    except (CopernicusAPIError, CopernicusConfigurationError, ValueError) as error:
        raise _raise_service_error(error) from None


@router.get(
    "/search/sentinel-1",
    response_model=SatelliteSearchResponse,
    summary="Search the Sentinel-1 Catalog",
    description="Returns request-time Catalog metadata only; it does not request or verify imagery.",
)
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
        return _satellite_search_response(
            copernicus_service.search_sentinel1(
                start_date=start_date,
                end_date=end_date,
                latitude=latitude,
                longitude=longitude,
                bbox=_bbox(west, south, east, north),
                limit=limit,
            ),
            latitude=latitude,
            longitude=longitude,
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
    request_time = datetime.now().astimezone()
    return Response(
        content=content,
        media_type="image/tiff",
        headers={
            "Content-Disposition": "inline; filename=satellite-aoi.tiff",
            "X-Data-Provider": "Copernicus Data Space",
            "X-Request-Time": utc_isoformat(request_time) or "",
            "X-Acquisition-Time": "UNRESOLVED",
            "X-Requested-Time-Range": f"{start_date.isoformat()}/{end_date.isoformat()}",
            "X-Imagery-Time-Limitation": (
                "Process API output does not identify a single source-scene acquisition time; "
                "the requested interval is not an acquisition timestamp."
            ),
        },
    )
