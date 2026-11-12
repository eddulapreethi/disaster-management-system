import math
from datetime import datetime, timezone

from app.schemas.provider import LocationCoverageResponse, ProviderCoverage
from app.services.gis_readiness_service import STUDY_BOUNDS


def build_location_coverage(latitude: float, longitude: float) -> LocationCoverageResponse:
    if isinstance(latitude, bool) or isinstance(longitude, bool):
        raise ValueError("Latitude and longitude must be valid WGS 84 coordinates.")
    try:
        latitude = float(latitude)
        longitude = float(longitude)
    except (TypeError, ValueError) as error:
        raise ValueError("Latitude and longitude must be valid WGS 84 coordinates.") from error
    if (
        not math.isfinite(latitude)
        or not math.isfinite(longitude)
        or not -90 <= latitude <= 90
        or not -180 <= longitude <= 180
    ):
        raise ValueError("Latitude and longitude must be valid WGS 84 coordinates.")

    checked_at = datetime.now(timezone.utc)
    west, south, east, north = STUDY_BOUNDS
    within_kochi_reference_extent = west <= longitude <= east and south <= latitude <= north
    providers = [
        ProviderCoverage(
            provider="Open-Meteo",
            product="Current weather point API",
            capability="weather",
            hazard=None,
            status="UNVERIFIED",
            scope="Coordinate-based request support only; geographic provider coverage is not verified.",
            details=(
                "No provider coverage catalog is available here. A successful point request would describe "
                "that request only, not establish coverage elsewhere."
            ),
            checked_at=checked_at,
            latitude=latitude,
            longitude=longitude,
        ),
        ProviderCoverage(
            provider="NWDP/NWIC CWC",
            product="Configured Krishna water-level and Andhra Pradesh rainfall resources",
            capability="hydrology",
            hazard="flood",
            status="UNVERIFIED",
            scope="Configured regional resources only; no verified station-to-selected-location mapping.",
            details="Do not treat these sources as covering this point or as Kochi observations without verified station metadata and a reviewed geographic match.",
            checked_at=checked_at,
            latitude=latitude,
            longitude=longitude,
        ),
        ProviderCoverage(
            provider="Local GIS",
            product="Kochi reference overlays",
            capability="reference_gis",
            hazard=None,
            status="SUPPORTED" if within_kochi_reference_extent else "UNSUPPORTED",
            scope="Kochi study-area reference layers only; not hazard or prediction coverage.",
            details=(
                "The point is inside the configured Kochi study-area extent. This indicates regional reference-layer scope only."
                if within_kochi_reference_extent
                else "No local reference GIS coverage is configured for this point."
            ),
            checked_at=checked_at,
            latitude=latitude,
            longitude=longitude,
        ),
    ]
    prediction_coverage = (
        (
            "flood",
            "Flood prediction",
            "Flood model readiness remains NOT_READY. No score is calculated or saved.",
        ),
        (
            "wildfire",
            "Wildfire prediction",
            "Only an unvalidated demonstrator heuristic exists; no regional prediction coverage is verified.",
        ),
        (
            "storm",
            "Storm prediction",
            "Only an unvalidated demonstrator heuristic exists; no regional prediction coverage is verified.",
        ),
        (
            "cyclone",
            "Cyclone prediction",
            "No hazard-specific cyclone prediction service or regional coverage is configured.",
        ),
        (
            "heatwave",
            "Heatwave prediction",
            "No hazard-specific heatwave prediction service or regional coverage is configured.",
        ),
        (
            "drought",
            "Drought prediction",
            "No hazard-specific drought prediction service or regional coverage is configured.",
        ),
        (
            "other",
            "Other hazard prediction",
            "No hazard-specific prediction service or regional coverage is configured.",
        ),
    )
    providers.extend(
        ProviderCoverage(
            provider="DisasterGuard AI",
            product=product,
            capability="prediction",
            hazard=hazard,
            status="UNAVAILABLE",
            scope=f"{product} is not available as a validated operational prediction for any location.",
            details=details,
            checked_at=checked_at,
            latitude=latitude,
            longitude=longitude,
        )
        for hazard, product, details in prediction_coverage
    )
    return LocationCoverageResponse(
        latitude=latitude,
        longitude=longitude,
        checked_at=checked_at,
        providers=providers,
    )
