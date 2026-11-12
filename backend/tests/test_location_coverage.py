import math

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.coverage import router
from app.schemas.provider import coverage_status_from_freshness
from app.services.coverage_service import build_location_coverage
from app.utils.authentication import get_current_user


def _client(authenticated: bool = True) -> TestClient:
    application = FastAPI()
    application.include_router(router, prefix="/api")
    if authenticated:
        application.dependency_overrides[get_current_user] = lambda: object()
    return TestClient(application)


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [
        (40.7128, -74.0060),
        (-33.8688, 151.2093),
        (51.5072, -0.1276),
        (-1.2921, 36.8219),
        (35.6762, 139.6503),
        (90, 180),
        (-90, -180),
    ],
)
def test_coverage_contract_accepts_valid_coordinates_worldwide(latitude, longitude) -> None:
    result = build_location_coverage(latitude, longitude)

    assert result.latitude == latitude
    assert result.longitude == longitude
    assert result.coordinate_reference_system == "OGC:CRS84"


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [(91, 0), (0, 181), (math.nan, 0), (0, math.inf), (True, 0)],
)
def test_coverage_contract_rejects_invalid_coordinates(latitude, longitude) -> None:
    with pytest.raises(ValueError, match="valid WGS 84"):
        build_location_coverage(latitude, longitude)


def test_provider_coverage_is_independent_and_region_limited() -> None:
    kochi = build_location_coverage(9.95, 76.25)
    global_point = build_location_coverage(-33.8688, 151.2093)

    kochi_statuses = {(item.capability, item.hazard): item.status for item in kochi.providers}
    global_statuses = {(item.capability, item.hazard): item.status for item in global_point.providers}

    assert kochi_statuses[("weather", None)] == "UNVERIFIED"
    assert kochi_statuses[("hydrology", "flood")] == "UNVERIFIED"
    assert kochi_statuses[("reference_gis", None)] == "SUPPORTED"
    assert kochi_statuses[("prediction", "flood")] == "UNAVAILABLE"
    assert kochi_statuses[("prediction", "wildfire")] == "UNAVAILABLE"
    assert kochi_statuses[("prediction", "storm")] == "UNAVAILABLE"
    assert kochi_statuses[("prediction", "cyclone")] == "UNAVAILABLE"
    assert kochi_statuses[("prediction", "heatwave")] == "UNAVAILABLE"
    assert kochi_statuses[("prediction", "drought")] == "UNAVAILABLE"
    assert global_statuses[("reference_gis", None)] == "UNSUPPORTED"
    assert global_statuses[("hydrology", "flood")] == "UNVERIFIED"
    assert global_statuses[("prediction", "flood")] == "UNAVAILABLE"
    assert all(
        "Kochi" in item.scope or item.capability != "reference_gis"
        for item in kochi.providers
    )


def test_coverage_status_tracks_point_weather_freshness() -> None:
    assert coverage_status_from_freshness("READY") == "SUPPORTED"
    assert coverage_status_from_freshness("STALE") == "STALE"
    assert coverage_status_from_freshness("UNAVAILABLE") == "UNAVAILABLE"
    assert coverage_status_from_freshness("ERROR") == "UNAVAILABLE"
    assert coverage_status_from_freshness("UNKNOWN") == "UNVERIFIED"


def test_coverage_endpoint_is_authenticated_and_returns_provider_scopes() -> None:
    with _client() as client:
        response = client.get("/api/coverage", params={"latitude": -33.8688, "longitude": 151.2093})

    assert response.status_code == 200
    payload = response.json()
    assert payload["coordinate_reference_system"] == "OGC:CRS84"
    assert payload["latitude"] == -33.8688
    assert {item["capability"] for item in payload["providers"]} == {
        "weather",
        "hydrology",
        "reference_gis",
        "prediction",
    }
    assert {item["hazard"] for item in payload["providers"] if item["capability"] == "prediction"} == {
        "flood",
        "wildfire",
        "storm",
        "cyclone",
        "heatwave",
        "drought",
        "other",
    }
    weather_scope = next(item for item in payload["providers"] if item["capability"] == "weather")
    assert weather_scope["status"] == "UNVERIFIED"
    assert "not establish coverage elsewhere" in weather_scope["details"]

    with _client(authenticated=False) as client:
        assert client.get("/api/coverage", params={"latitude": 0, "longitude": 0}).status_code == 401
