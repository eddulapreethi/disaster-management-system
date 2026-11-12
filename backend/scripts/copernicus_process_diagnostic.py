"""Verify Copernicus OAuth, Catalog, and bounded Sentinel-2 Process API access."""

from __future__ import annotations

import argparse
import importlib
import io
import math
import os
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

import requests
from PIL import Image, UnidentifiedImageError
from requests.exceptions import ConnectTimeout, ReadTimeout, RequestException

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Importing app loads the configured backend/.env file.
importlib.import_module("app")
from app.services.copernicus_service import (  # noqa: E402
    CATALOG_SEARCH_URL,
    DEFAULT_CONNECT_TIMEOUT_SECONDS,
    DEFAULT_READ_TIMEOUT_SECONDS,
    PROCESS_URL,
    TOKEN_URL,
    CopernicusAPIError,
    CopernicusConfigurationError,
    CopernicusSceneNotFoundError,
    CopernicusService,
)

DEFAULT_IMAGE_DIMENSION = 128
CATALOG_RESULT_LIMIT = 5
MAX_IMAGE_BYTES = 16 * 1024 * 1024
SAFE_ERROR_CODES = {
    "access_denied",
    "forbidden",
    "invalid_client",
    "invalid_grant",
    "invalid_request",
    "invalid_scope",
    "invalid_token",
    "server_error",
    "temporarily_unavailable",
    "unauthorized",
    "unauthorized_client",
}


class RecordingSession(requests.Session):
    """Record response metadata only; never retain or expose request headers."""

    def __init__(self, delegate: Any) -> None:
        super().__init__()
        self._delegate = delegate
        self.responses: list[dict[str, Any]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> Any:
        try:
            response = self._delegate.request(method, url, **kwargs)
        except RequestException as error:
            if isinstance(error, ReadTimeout):
                error_type = "ReadTimeout"
            elif isinstance(error, ConnectTimeout):
                error_type = "ConnectTimeout"
            else:
                error_type = type(error).__name__
            self.responses.append(
                {"url": url, "status_code": None, "content_type": None, "error_type": error_type}
            )
            raise
        self.responses.append(
            {
                "url": url,
                "status_code": response.status_code,
                "content_type": response.headers.get("Content-Type"),
                "error_code": _safe_error_code(response) if not response.ok else None,
                "error_type": None,
            }
        )
        return response

    def response_for(self, url: str) -> dict[str, Any] | None:
        return next((record for record in reversed(self.responses) if record["url"] == url), None)

    def close(self) -> None:
        close = getattr(self._delegate, "close", None)
        if close:
            close()
        super().close()


def _safe_error_code(response: Any | None) -> str:
    if response is None:
        return "unavailable"
    try:
        payload = response.json()
    except (AttributeError, ValueError):
        return "unavailable"
    code = payload.get("error") if isinstance(payload, dict) else None
    return code if isinstance(code, str) and code in SAFE_ERROR_CODES else "unavailable"


def _network_error_code(record: dict[str, Any] | None) -> str:
    if record and record.get("error_type") == "ReadTimeout":
        return "read_timeout"
    if record and record.get("error_type") == "ConnectTimeout":
        return "connect_timeout"
    if record and record.get("error_type") == "Timeout":
        return "timeout"
    return "network_error"


def _effective_timeout(
    override: float | None,
    environment_value: str | None,
    fallback: float,
    setting: str,
) -> float:
    value = override if override is not None else environment_value
    if value is None:
        return fallback
    if isinstance(value, str) and not value.strip():
        return fallback
    try:
        timeout = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{setting} must be a positive finite number.") from error
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError(f"{setting} must be a positive finite number.")
    return timeout


def _validate_location(
    latitude: float | None,
    longitude: float | None,
    bbox: tuple[float, float, float, float] | None,
) -> tuple[float, float, float, float]:
    has_point = latitude is not None or longitude is not None
    complete_point = latitude is not None and longitude is not None
    if has_point != complete_point or (bbox is not None and complete_point) or (bbox is None and not complete_point):
        raise ValueError("Provide either both latitude and longitude, or one bbox.")
    if bbox is None:
        lat, lon = float(latitude), float(longitude)
        if not math.isfinite(lat) or not -90 <= lat <= 90:
            raise ValueError("latitude must be between -90 and 90.")
        if not math.isfinite(lon) or not -180 <= lon <= 180:
            raise ValueError("longitude must be between -180 and 180.")
        return (
            max(-180.0, lon - 0.01),
            max(-90.0, lat - 0.01),
            min(180.0, lon + 0.01),
            min(90.0, lat + 0.01),
        )
    west, south, east, north = (float(value) for value in bbox)
    if not all(math.isfinite(value) for value in (west, south, east, north)):
        raise ValueError("bbox coordinates must be finite.")
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise ValueError("bbox must satisfy -180<=west<east<=180 and -90<=south<north<=90.")
    if east - west > 0.25 or north - south > 0.25:
        raise ValueError("bbox width and height must each be at most 0.25 degrees.")
    return west, south, east, north


def _validate_dates(start_date: date, end_date: date) -> None:
    if start_date > end_date:
        raise ValueError("start-date must be before or equal to end-date.")
    if end_date > datetime.now(timezone.utc).date() + timedelta(days=1):
        raise ValueError("end-date cannot be more than one day in the future.")


def _validate_geotiff(image_bytes: bytes, expected_width: int, expected_height: int) -> tuple[bool, str]:
    if not image_bytes:
        return False, "empty_image"
    if len(image_bytes) > MAX_IMAGE_BYTES:
        return False, "image_too_large"
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            image_format = image.format
            image.verify()
        with Image.open(io.BytesIO(image_bytes)) as image:
            width, height = image.size
            tags = image.tag_v2
    except (OSError, UnidentifiedImageError, ValueError):
        return False, "invalid_image"
    if image_format not in {"TIFF", "TIF"}:
        return False, "not_tiff"
    if width != expected_width or height != expected_height:
        return False, f"dimensions_mismatch:{width}x{height}"
    has_georeferencing = 34264 in tags or (33550 in tags and 33922 in tags)
    if not has_georeferencing or 34735 not in tags:
        return False, "missing_georeferencing_tags"
    return True, f"{width}x{height}"


def run_diagnostic(
    *,
    latitude: float | None = None,
    longitude: float | None = None,
    bbox: tuple[float, float, float, float] | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    cloud_coverage: float | None = None,
    width: int = DEFAULT_IMAGE_DIMENSION,
    height: int = DEFAULT_IMAGE_DIMENSION,
    connect_timeout_seconds: float | None = None,
    read_timeout_seconds: float | None = None,
    output_dir: str | Path | None = None,
    session: Any | None = None,
    environment: Mapping[str, str] | None = None,
    output: Callable[[str], None] = print,
) -> int:
    """Run one OAuth request, one Catalog query, and at most one Process request."""
    env = os.environ if environment is None else environment
    client_id = (env.get("COPERNICUS_CLIENT_ID") or "").strip()
    client_secret = (env.get("COPERNICUS_CLIENT_SECRET") or "").strip()
    output(f"Client ID present: {'yes' if client_id else 'no'}")
    output(f"Client secret present: {'yes' if client_secret else 'no'}")
    if not client_id or not client_secret:
        output("OAuth succeeded: no (credentials unavailable; no external request made)")
        output("Catalog search succeeded: no (not attempted)")
        output("Process API request succeeded: no (not attempted)")
        output("Valid GeoTIFF received: no")
        output("Imagery tied to selected Catalog item: no")
        return 2

    try:
        connect_timeout = _effective_timeout(
            connect_timeout_seconds,
            env.get("COPERNICUS_CONNECT_TIMEOUT_SECONDS"),
            DEFAULT_CONNECT_TIMEOUT_SECONDS,
            "COPERNICUS_CONNECT_TIMEOUT_SECONDS",
        )
        read_timeout = _effective_timeout(
            read_timeout_seconds,
            env.get("COPERNICUS_READ_TIMEOUT_SECONDS"),
            DEFAULT_READ_TIMEOUT_SECONDS,
            "COPERNICUS_READ_TIMEOUT_SECONDS",
        )
        requested_bbox = _validate_location(latitude, longitude, bbox)
        today = datetime.now(timezone.utc).date()
        selected_end_date = end_date or today
        selected_start_date = start_date or (selected_end_date - timedelta(days=30))
        _validate_dates(selected_start_date, selected_end_date)
        if (
            isinstance(width, bool)
            or isinstance(height, bool)
            or not isinstance(width, int)
            or not isinstance(height, int)
            or not (1 <= width <= 1024 and 1 <= height <= 1024)
        ):
            raise ValueError("width and height must be integers between 1 and 1024.")
        if cloud_coverage is not None and (
            not math.isfinite(cloud_coverage) or not 0 <= cloud_coverage <= 100
        ):
            raise ValueError("cloud-coverage must be between 0 and 100.")
    except (TypeError, ValueError) as error:
        output(f"Input error: {error}")
        return 2
    output(f"Connect timeout seconds: {connect_timeout:g}")
    output(f"Read timeout seconds: {read_timeout:g}")

    recorder = RecordingSession(session or requests.Session())
    service = CopernicusService(
        client_id=client_id,
        client_secret=client_secret,
        connect_timeout_seconds=connect_timeout,
        read_timeout_seconds=read_timeout,
        retry_unauthorized=False,
        session=recorder,
    )
    try:
        service.authenticate()
    except (CopernicusConfigurationError, CopernicusAPIError):
        auth_record = recorder.response_for(TOKEN_URL)
        if auth_record and auth_record["status_code"] is not None:
            output(f"OAuth HTTP status: {auth_record['status_code']}")
            error_code = auth_record["error_code"]
            if error_code is None and auth_record["status_code"] == 200:
                error_code = "malformed_response"
            output(f"OAuth error code: {error_code or 'unavailable'}")
        else:
            output("OAuth HTTP status: unavailable")
            output(f"OAuth error code: {_network_error_code(auth_record)}")
        output("OAuth succeeded: no")
        output("Catalog search succeeded: no (not attempted)")
        output("Process API request succeeded: no (not attempted)")
        output("Valid GeoTIFF received: no")
        output("Imagery tied to selected Catalog item: no")
        recorder.close()
        return 3

    auth_record = recorder.response_for(TOKEN_URL)
    output(f"OAuth HTTP status: {auth_record['status_code'] if auth_record else 'unavailable'}")
    output("OAuth succeeded: yes")

    catalog_result: dict[str, Any] | None = None
    try:
        catalog_result = service.search_sentinel2(
            start_date=selected_start_date,
            end_date=selected_end_date,
            bbox=requested_bbox,
            cloud_coverage=cloud_coverage,
            limit=CATALOG_RESULT_LIMIT,
        )
    except (CopernicusAPIError, ValueError):
        catalog_record = recorder.response_for(CATALOG_SEARCH_URL)
        if catalog_record and catalog_record["status_code"] is not None:
            output(f"Catalog HTTP status: {catalog_record['status_code']}")
            error_code = catalog_record["error_code"]
            if error_code is None and catalog_record["status_code"] == 200:
                error_code = "malformed_response"
            output(f"Catalog error code: {error_code or 'unavailable'}")
        else:
            output("Catalog HTTP status: unavailable")
            output(f"Catalog error code: {_network_error_code(catalog_record)}")
        output("Catalog search succeeded: no")
        output("Process API request succeeded: no (not attempted)")
        output("Valid GeoTIFF received: no")
        output("Imagery tied to selected Catalog item: no")
        recorder.close()
        return 4

    catalog_record = recorder.response_for(CATALOG_SEARCH_URL)
    catalog_features = catalog_result["features"]
    output(f"Catalog HTTP status: {catalog_record['status_code'] if catalog_record else 'unavailable'}")
    output(f"Catalog features returned: {len(catalog_features)}")
    output(f"Catalog fetched at: {catalog_result['fetched_at']}")
    output("Catalog search succeeded: yes")
    try:
        selected, acquisition_time = service.select_sentinel2_catalog_scene(
            catalog_result,
            cloud_coverage=cloud_coverage,
        )
    except CopernicusSceneNotFoundError:
        output("Catalog item ID: unavailable")
        output("Acquisition time: unavailable")
        output("Process API request succeeded: no (no usable scene found)")
        output("Valid GeoTIFF received: no")
        output("Imagery tied to selected Catalog item: no")
        recorder.close()
        return 5

    item_id = selected["id"]
    acquisition_iso = acquisition_time.isoformat().replace("+00:00", "Z")
    output(f"Catalog item ID: {item_id}")
    output(f"Acquisition time: {acquisition_iso}")
    process_requested_at = datetime.now(timezone.utc)
    output(f"Process request time: {process_requested_at.isoformat().replace('+00:00', 'Z')}")
    try:
        image_bytes = service.get_satellite_image(
            collection="sentinel-2",
            bbox=requested_bbox,
            start_date=acquisition_time,
            end_date=acquisition_time + timedelta(seconds=1),
            cloud_coverage=cloud_coverage,
            width=width,
            height=height,
        )
    except (CopernicusAPIError, ValueError):
        process_record = recorder.response_for(PROCESS_URL)
        if process_record and process_record["status_code"] is not None:
            output(f"Process API HTTP status: {process_record['status_code']}")
            error_code = process_record["error_code"]
            if error_code is None and process_record["status_code"] == 200:
                content_type = (process_record["content_type"] or "").lower()
                error_code = (
                    "empty_response"
                    if content_type.startswith(("image/tiff", "image/geotiff", "application/geotiff"))
                    else "unexpected_content_type"
                )
            output(f"Process API error code: {error_code or 'unavailable'}")
            output(f"Process API content type: {process_record['content_type'] or 'unavailable'}")
        else:
            output("Process API HTTP status: unavailable")
            output(f"Process API error code: {_network_error_code(process_record)}")
            output("Process API content type: unavailable")
        output("Process API request succeeded: no")
        output("Valid GeoTIFF received: no")
        output("Imagery tied to selected Catalog item: no")
        recorder.close()
        return 6

    process_record = recorder.response_for(PROCESS_URL)
    downloaded_at = datetime.now(timezone.utc)
    status = process_record["status_code"] if process_record else None
    content_type = process_record["content_type"] if process_record else None
    output(f"Process API HTTP status: {status if status is not None else 'unavailable'}")
    output(f"Process API content type: {content_type or 'unavailable'}")
    output(f"Image response received at: {downloaded_at.isoformat().replace('+00:00', 'Z')}")
    output("Process API request succeeded: yes")

    valid_tiff, image_details = _validate_geotiff(image_bytes, width, height)
    output(f"Valid GeoTIFF received: {'yes' if valid_tiff else 'no'}")
    output(f"GeoTIFF dimensions: {image_details}")
    saved_path: Path | None = None
    if valid_tiff:
        try:
            destination = Path(output_dir) if output_dir is not None else Path(
                tempfile.mkdtemp(prefix="disasterguard-copernicus-process-")
            )
            destination.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix="sentinel-2-process-test-",
                suffix=".tiff",
                dir=destination,
                delete=False,
            ) as output_file:
                output_file.write(image_bytes)
                saved_path = Path(output_file.name)
            output(f"Image saved: {saved_path}")
        except OSError as error:
            output(f"Image saved: no ({type(error).__name__})")
            recorder.close()
            return 7
    else:
        output("Image saved: no (response was not a valid TIFF of the requested dimensions)")

    output("Imagery tied to selected Catalog item: no")
    output(
        "Reason: Process API selects/mosaics by AOI and time range; the selected Catalog ID is a reference, "
        "not a source-item pin."
    )
    output("Attribution: follow Copernicus Data Space terms and conditions.")
    recorder.close()
    return 0 if valid_tiff and saved_path is not None else 8


def _date_argument(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD format") from error


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    location = parser.add_mutually_exclusive_group(required=True)
    location.add_argument("--latitude", type=float)
    location.add_argument("--bbox", nargs=4, type=float, metavar=("WEST", "SOUTH", "EAST", "NORTH"))
    parser.add_argument("--longitude", type=float)
    parser.add_argument("--start-date", type=_date_argument)
    parser.add_argument("--end-date", type=_date_argument)
    parser.add_argument("--cloud-coverage", type=float)
    parser.add_argument("--width", type=int, default=DEFAULT_IMAGE_DIMENSION)
    parser.add_argument("--height", type=int, default=DEFAULT_IMAGE_DIMENSION)
    parser.add_argument("--connect-timeout", type=float)
    parser.add_argument("--read-timeout", type=float)
    parser.add_argument("--output-dir", type=Path)
    return parser


def main() -> int:
    arguments = _parser().parse_args()
    bbox = tuple(arguments.bbox) if arguments.bbox is not None else None
    return run_diagnostic(
        latitude=arguments.latitude,
        longitude=arguments.longitude,
        bbox=bbox,
        start_date=arguments.start_date,
        end_date=arguments.end_date,
        cloud_coverage=arguments.cloud_coverage,
        width=arguments.width,
        height=arguments.height,
        connect_timeout_seconds=arguments.connect_timeout,
        read_timeout_seconds=arguments.read_timeout,
        output_dir=arguments.output_dir,
    )


if __name__ == "__main__":
    raise SystemExit(main())
