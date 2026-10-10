import json
import logging
import math
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"


def _normalize_result(item: dict[str, Any]) -> dict[str, Any]:
    name = str(item.get("name") or "").strip()
    if not name:
        raise ValueError("Geocoding result is missing a place name.")

    try:
        latitude = float(item.get("latitude"))
        longitude = float(item.get("longitude"))
    except (TypeError, ValueError) as error:
        raise ValueError("Geocoding result is missing valid coordinates.") from error

    if not math.isfinite(latitude) or not -90 <= latitude <= 90:
        raise ValueError(f"Geocoding result has an invalid latitude: {latitude!r}.")
    if not math.isfinite(longitude) or not -180 <= longitude <= 180:
        raise ValueError(f"Geocoding result has an invalid longitude: {longitude!r}.")

    admin1 = item.get("admin1") or item.get("admin_name")
    admin2 = item.get("admin2")
    country = item.get("country") or item.get("country_code") or "Unknown"
    display_name = ", ".join(part for part in [name, admin1, admin2, country] if part)

    return {
        "id": item.get("id"),
        "name": name,
        "admin1": admin1,
        "admin2": admin2,
        "country": country,
        "latitude": latitude,
        "longitude": longitude,
        "display_name": display_name,
        "timezone": item.get("timezone"),
        "population": item.get("population"),
        "elevation_m": item.get("elevation"),
        "feature_code": item.get("feature_code"),
    }


def search_locations(query: str, limit: int = 8) -> list[dict[str, Any]]:
    """Search for a place name using the public Open-Meteo geocoding API."""
    cleaned = (query or "").strip()
    if not cleaned:
        return []
    if len(cleaned) < 2:
        return []

    try:
        count = max(1, min(int(limit), 10))
    except (TypeError, ValueError) as error:
        raise ValueError("Location search limit must be an integer between 1 and 10.") from error

    params = urlencode({
        "name": cleaned,
        "count": count,
        "language": "en",
        "format": "json",
    })
    request = Request(
        f"{GEOCODING_URL}?{params}",
        headers={"User-Agent": "DisasterGuard-AI/1.0"},
    )
    try:
        with urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
        logger.warning("Location search API unavailable for query %r: %s", cleaned, error)
        raise RuntimeError(f"Location search failed: {error}") from error

    results = payload.get("results")
    if not isinstance(results, list):
        return []

    normalized: list[dict[str, Any]] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        try:
            normalized.append(_normalize_result(item))
        except ValueError as error:
            logger.warning("Skipping malformed geocoding result for %r: %s", cleaned, error)
    return normalized
