from __future__ import annotations

import logging
import math
import os
import threading
import time
from datetime import date, datetime, time as datetime_time, timedelta, timezone
from typing import Any

import requests
from requests import Response
from requests.exceptions import RequestException

logger = logging.getLogger(__name__)

TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
SENTINEL_HUB_BASE_URL = "https://sh.dataspace.copernicus.eu"
CATALOG_SEARCH_URL = f"{SENTINEL_HUB_BASE_URL}/catalog/v1/search"
PROCESS_URL = f"{SENTINEL_HUB_BASE_URL}/process/v1"
COLLECTIONS = {"sentinel-1": "sentinel-1-grd", "sentinel-2": "sentinel-2-l2a"}
DEFAULT_TIMEOUT_SECONDS = 20
MAX_IMAGE_DIMENSION = 1024


class CopernicusError(RuntimeError):
    """Safe error raised for Copernicus integration failures."""


class CopernicusConfigurationError(CopernicusError):
    """Required backend OAuth configuration is missing."""


class CopernicusAPIError(CopernicusError):
    """Copernicus returned an error or could not be reached."""


class CopernicusService:
    """Sentinel Hub OAuth, Catalog search and bounded Process API client."""

    def __init__(
        self,
        *,
        client_id: str | None = None,
        client_secret: str | None = None,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        session: requests.Session | None = None,
    ) -> None:
        self._client_id_override = client_id
        self._client_secret_override = client_secret
        self._timeout_seconds = timeout_seconds
        self._session = session or requests.Session()
        self._token: str | None = None
        self._token_expires_at = 0.0
        self._token_lock = threading.Lock()

    def _credentials(self) -> tuple[str, str]:
        client_id = self._client_id_override or os.getenv("COPERNICUS_CLIENT_ID", "").strip()
        client_secret = self._client_secret_override or os.getenv("COPERNICUS_CLIENT_SECRET", "").strip()
        if not client_id or not client_secret:
            raise CopernicusConfigurationError(
                "Copernicus OAuth is not configured. Set COPERNICUS_CLIENT_ID and "
                "COPERNICUS_CLIENT_SECRET in backend/.env."
            )
        return client_id, client_secret

    def authenticate(self, *, force_refresh: bool = False) -> str:
        """Fetch and cache an OAuth token; callers must never return/log it."""
        client_id, client_secret = self._credentials()
        with self._token_lock:
            now = time.monotonic()
            if not force_refresh and self._token and now < self._token_expires_at:
                return self._token
            try:
                response = self._session.post(
                    TOKEN_URL,
                    data={
                        "grant_type": "client_credentials",
                        "client_id": client_id,
                        "client_secret": client_secret,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    timeout=self._timeout_seconds,
                )
                self._raise_for_status(response, "OAuth token request")
                payload = response.json()
            except (RequestException, ValueError) as error:
                logger.warning("Copernicus OAuth request failed (%s).", type(error).__name__)
                raise CopernicusAPIError(
                    "Copernicus authentication failed. Check the OAuth client configuration and network connection."
                ) from None

            access_token = payload.get("access_token") if isinstance(payload, dict) else None
            if not isinstance(access_token, str) or not access_token:
                raise CopernicusAPIError("Copernicus OAuth response did not contain an access token.")
            try:
                expires_in = max(60, int(payload.get("expires_in", 300)))
            except (TypeError, ValueError):
                expires_in = 300
            self._token = access_token
            self._token_expires_at = time.monotonic() + max(1, expires_in - 60)
            logger.info("Copernicus OAuth succeeded; access token cached until shortly before expiry.")
            return access_token

    def search_sentinel2(
        self,
        *,
        start_date: date | datetime | str,
        end_date: date | datetime | str,
        latitude: float | None = None,
        longitude: float | None = None,
        bbox: tuple[float, float, float, float] | list[float] | None = None,
        cloud_coverage: float | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        return self._search(
            collection=COLLECTIONS["sentinel-2"],
            start_date=start_date,
            end_date=end_date,
            latitude=latitude,
            longitude=longitude,
            bbox=bbox,
            cloud_coverage=cloud_coverage,
            limit=limit,
        )

    def search_sentinel1(
        self,
        *,
        start_date: date | datetime | str,
        end_date: date | datetime | str,
        latitude: float | None = None,
        longitude: float | None = None,
        bbox: tuple[float, float, float, float] | list[float] | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        return self._search(
            collection=COLLECTIONS["sentinel-1"],
            start_date=start_date,
            end_date=end_date,
            latitude=latitude,
            longitude=longitude,
            bbox=bbox,
            cloud_coverage=None,
            limit=limit,
        )

    def get_satellite_image(
        self,
        *,
        collection: str,
        latitude: float,
        longitude: float,
        start_date: date | datetime | str,
        end_date: date | datetime | str,
        cloud_coverage: float | None = None,
        width: int = 512,
        height: int = 512,
    ) -> bytes:
        """Request only a small AOI image, never an entire Sentinel product."""
        normalized = collection.lower().replace("_", "-")
        if normalized in {"sentinel-1", COLLECTIONS["sentinel-1"]}:
            collection_id, evalscript = COLLECTIONS["sentinel-1"], _SENTINEL1_EVALSCRIPT
        elif normalized in {"sentinel-2", COLLECTIONS["sentinel-2"]}:
            collection_id, evalscript = COLLECTIONS["sentinel-2"], _SENTINEL2_EVALSCRIPT
        else:
            raise ValueError("collection must be sentinel-1 or sentinel-2.")

        lat, lon = _validate_coordinates(latitude, longitude)
        _validate_date_range(start_date, end_date)
        _validate_cloud_coverage(cloud_coverage)
        _validate_dimensions(width, height)
        data_filter: dict[str, Any] = {"timeRange": {"from": _iso_datetime(start_date, is_end=False), "to": _iso_datetime(end_date, is_end=True)}}
        if cloud_coverage is not None and collection_id == COLLECTIONS["sentinel-2"]:
            data_filter["maxCloudCoverage"] = float(cloud_coverage)

        request_body = {
            "input": {
                "bounds": {
                    "bbox": _point_bbox(lon, lat),
                    "properties": {"crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84"},
                },
                "data": [{"type": collection_id, "dataFilter": data_filter}],
            },
            "output": {
                "width": width,
                "height": height,
                "responses": [{"identifier": "default", "format": {"type": "image/tiff"}}],
            },
            "evalscript": evalscript,
        }
        return self._authorized_request("POST", PROCESS_URL, json=request_body, accept="image/tiff").content

    def _search(
        self,
        *,
        collection: str,
        start_date: date | datetime | str,
        end_date: date | datetime | str,
        latitude: float | None,
        longitude: float | None,
        bbox: tuple[float, float, float, float] | list[float] | None,
        cloud_coverage: float | None,
        limit: int,
    ) -> dict[str, Any]:
        search_bbox = _resolve_bbox(latitude, longitude, bbox)
        _validate_date_range(start_date, end_date)
        _validate_cloud_coverage(cloud_coverage)
        if isinstance(limit, bool) or not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100.")

        body: dict[str, Any] = {
            "bbox": search_bbox,
            "datetime": f"{_iso_datetime(start_date, is_end=False)}/{_iso_datetime(end_date, is_end=True)}",
            "collections": [collection],
            "limit": limit,
            "fields": {
                "include": [
                    "id", "collection", "geometry", "bbox", "assets",
                    "properties.datetime", "properties.eo:cloud_cover",
                    "properties.platform", "properties.instruments",
                ]
            },
        }
        if cloud_coverage is not None and collection == COLLECTIONS["sentinel-2"]:
            body["filter-lang"] = "cql2-text"
            body["filter"] = f"eo:cloud_cover <= {float(cloud_coverage):g}"

        response = self._authorized_request("POST", CATALOG_SEARCH_URL, json=body)
        try:
            payload = response.json()
        except ValueError:
            raise CopernicusAPIError("Copernicus Catalog returned invalid JSON.") from None
        if not isinstance(payload, dict) or not isinstance(payload.get("features", []), list):
            raise CopernicusAPIError("Copernicus Catalog returned an unexpected response format.")
        return {
            "collection": collection,
            "features": [_public_feature(item) for item in payload.get("features", []) if isinstance(item, dict)],
            "context": payload.get("context", {}),
            "query": {
                "bbox": search_bbox,
                "start_date": _iso_datetime(start_date, is_end=False),
                "end_date": _iso_datetime(end_date, is_end=True),
                "cloud_coverage": cloud_coverage if collection == COLLECTIONS["sentinel-2"] else None,
                "limit": limit,
            },
        }

    def _authorized_request(self, method: str, url: str, *, accept: str = "application/geo+json", **kwargs: Any) -> Response:
        for attempt in range(2):
            token = self.authenticate(force_refresh=bool(attempt))
            headers = dict(kwargs.pop("headers", {}) or {})
            headers["Authorization"] = f"Bearer {token}"
            headers.setdefault("Accept", accept)
            try:
                response = self._session.request(
                    method, url, headers=headers, timeout=self._timeout_seconds, **kwargs
                )
            except RequestException as error:
                logger.warning("Copernicus API request failed (%s).", type(error).__name__)
                raise CopernicusAPIError("Copernicus request failed due to a network or timeout error.") from None
            if response.status_code == 401 and attempt == 0:
                with self._token_lock:
                    self._token = None
                    self._token_expires_at = 0.0
                continue
            self._raise_for_status(response, "Copernicus API request")
            return response
        raise CopernicusAPIError("Copernicus authorization failed after refreshing the token.")

    @staticmethod
    def _raise_for_status(response: Response, operation: str) -> None:
        if response.ok:
            return
        status_code = response.status_code
        logger.warning("%s returned HTTP %s.", operation, status_code)
        if status_code == 429:
            raise CopernicusAPIError("Copernicus rate limit reached. Retry later.")
        if status_code in {401, 403}:
            raise CopernicusAPIError("Copernicus rejected the OAuth client or its permissions.")
        raise CopernicusAPIError(f"Copernicus request failed with HTTP {status_code}.")

    def is_configured(self) -> bool:
        client_id = self._client_id_override or os.getenv("COPERNICUS_CLIENT_ID", "").strip()
        client_secret = self._client_secret_override or os.getenv("COPERNICUS_CLIENT_SECRET", "").strip()
        return bool(client_id and client_secret)


service = CopernicusService()


def authenticate() -> dict[str, bool]:
    """Test OAuth configuration without returning the access token."""
    service.authenticate()
    return {"authenticated": True}


def search_sentinel2(**kwargs: Any) -> dict[str, Any]:
    return service.search_sentinel2(**kwargs)


def search_sentinel1(**kwargs: Any) -> dict[str, Any]:
    return service.search_sentinel1(**kwargs)


def get_satellite_image(**kwargs: Any) -> bytes:
    return service.get_satellite_image(**kwargs)


def is_configured() -> bool:
    return service.is_configured()


def _validate_coordinates(latitude: float, longitude: float) -> tuple[float, float]:
    lat, lon = float(latitude), float(longitude)
    if not math.isfinite(lat) or not -90 <= lat <= 90:
        raise ValueError("latitude must be between -90 and 90.")
    if not math.isfinite(lon) or not -180 <= lon <= 180:
        raise ValueError("longitude must be between -180 and 180.")
    return lat, lon


def _resolve_bbox(latitude: float | None, longitude: float | None, bbox: tuple[float, float, float, float] | list[float] | None) -> list[float]:
    if bbox is not None:
        if len(bbox) != 4:
            raise ValueError("bbox must be [west, south, east, north].")
        west, south, east, north = (float(value) for value in bbox)
        if not all(math.isfinite(value) for value in (west, south, east, north)):
            raise ValueError("bbox coordinates must be finite.")
        if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
            raise ValueError("bbox must satisfy -180<=west<east<=180 and -90<=south<north<=90.")
        return [west, south, east, north]
    if latitude is None or longitude is None:
        raise ValueError("Provide either bbox or both latitude and longitude.")
    lat, lon = _validate_coordinates(latitude, longitude)
    return _point_bbox(lon, lat)


def _point_bbox(longitude: float, latitude: float, half_size_degrees: float = 0.01) -> list[float]:
    return [
        max(-180.0, longitude - half_size_degrees),
        max(-90.0, latitude - half_size_degrees),
        min(180.0, longitude + half_size_degrees),
        min(90.0, latitude + half_size_degrees),
    ]


def _parse_datetime(value: date | datetime | str, *, end_of_date: bool = False) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, datetime_time.max if end_of_date else datetime_time.min, tzinfo=timezone.utc)
    else:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (TypeError, ValueError) as error:
            raise ValueError("Dates must be ISO-8601 dates or datetimes.") from error
        if end_of_date and len(value) == 10:
            parsed = datetime.combine(parsed.date(), datetime_time.max, tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _validate_date_range(start_date: date | datetime | str, end_date: date | datetime | str) -> None:
    start, end = _parse_datetime(start_date), _parse_datetime(end_date, end_of_date=True)
    if start > end:
        raise ValueError("start_date must be before or equal to end_date.")
    if end > datetime.now(timezone.utc) + timedelta(days=1):
        raise ValueError("end_date cannot be more than one day in the future.")


def _iso_datetime(value: date | datetime | str, *, is_end: bool) -> str:
    return _parse_datetime(value, end_of_date=is_end).isoformat().replace("+00:00", "Z")


def _validate_cloud_coverage(cloud_coverage: float | None) -> None:
    if cloud_coverage is not None:
        value = float(cloud_coverage)
        if not math.isfinite(value) or not 0 <= value <= 100:
            raise ValueError("cloud_coverage must be between 0 and 100.")


def _validate_dimensions(width: int, height: int) -> None:
    if isinstance(width, bool) or isinstance(height, bool) or not isinstance(width, int) or not isinstance(height, int):
        raise ValueError("Image width and height must be integers.")
    if width < 1 or height < 1 or width > MAX_IMAGE_DIMENSION or height > MAX_IMAGE_DIMENSION:
        raise ValueError(f"Image dimensions must be between 1 and {MAX_IMAGE_DIMENSION} pixels.")


def _public_feature(feature: dict[str, Any]) -> dict[str, Any]:
    properties = feature.get("properties") or {}
    assets = feature.get("assets") or {}
    safe_assets = {
        name: {key: asset[key] for key in ("title", "type", "roles") if key in asset}
        for name, asset in assets.items()
        if isinstance(asset, dict)
    }
    return {
        "id": feature.get("id"),
        "collection": feature.get("collection"),
        "sensing_time": properties.get("datetime"),
        "cloud_coverage": properties.get("eo:cloud_cover"),
        "platform": properties.get("platform"),
        "instruments": properties.get("instruments"),
        "bbox": feature.get("bbox"),
        "geometry": feature.get("geometry"),
        "assets": safe_assets,
    }


_SENTINEL2_EVALSCRIPT = """//VERSION=3
function setup() {
  return { input: [{ bands: [\"B04\", \"B03\", \"B02\"], units: \"DN\" }], output: { bands: 3, sampleType: \"UINT16\" } };
}
function evaluatePixel(sample) { return [sample.B04, sample.B03, sample.B02]; }
"""
_SENTINEL1_EVALSCRIPT = """//VERSION=3
function setup() {
  return { input: [{ bands: [\"VV\", \"VH\"], units: \"LINEAR_POWER\" }], output: { bands: 2, sampleType: \"FLOAT32\" } };
}
function evaluatePixel(sample) { return [sample.VV, sample.VH]; }
"""
