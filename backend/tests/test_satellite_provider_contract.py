import json
import logging
from datetime import date, datetime, timezone
from io import BytesIO
from unittest.mock import Mock
from urllib.parse import unquote

import pytest
from PIL import Image, TiffImagePlugin
from requests import Response
from requests.exceptions import ConnectTimeout, ReadTimeout, Timeout
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import satellite
from app.services.copernicus_service import (
    CATALOG_SEARCH_URL,
    TOKEN_URL,
    CopernicusAPIError,
    CopernicusConfigurationError,
    CopernicusSceneNotFoundError,
    CopernicusService,
    MAX_IMAGE_RESPONSE_BYTES,
    PROCESS_URL,
)
from app.utils.authentication import get_current_user


def _client() -> TestClient:
    application = FastAPI()
    application.include_router(satellite.router, prefix="/api")
    application.dependency_overrides[get_current_user] = lambda: object()
    return TestClient(application)


def _response(status_code: int, payload: dict) -> Mock:
    response = Mock(spec=Response)
    response.status_code = status_code
    response.ok = 200 <= status_code < 400
    response.json.return_value = payload
    response.iter_content.return_value = iter([response.content])
    return response


def _assert_bearer_header(request_call, token: str) -> None:
    authorization = request_call.kwargs["headers"].get("Authorization")
    if authorization != f"Bearer {token}":
        raise AssertionError("Copernicus request did not use the expected Bearer token.")


def _assert_not_exposed(text: str, *sensitive_values: str) -> None:
    if any(value and value in text for value in sensitive_values):
        raise AssertionError("Copernicus credentials or tokens appeared in output.")


def _geotiff(width: int, height: int) -> bytes:
    buffer = BytesIO()
    tags = TiffImagePlugin.ImageFileDirectory_v2()
    tags[33550] = (0.0001, 0.0001, 0.0)
    tags[33922] = (0.0, 0.0, 0.0, 20.0, 10.0, 0.0)
    tags[34735] = (1, 1, 0, 1)
    Image.new("RGB", (width, height), color=(1, 2, 3)).save(buffer, format="TIFF", tiffinfo=tags)
    return buffer.getvalue()


def test_oauth_success_uses_documented_client_credentials_form_and_catalog_bearer() -> None:
    token_response = _response(200, {"access_token": "mock-access-token", "expires_in": 3600})
    catalog_response = _response(
        200,
        {
            "features": [
                {
                    "id": "sentinel-item-verified",
                    "collection": "sentinel-2-l2a",
                    "properties": {
                        "datetime": "2026-10-25T06:12:34Z",
                        "eo:cloud_cover": 27.0,
                        "platform": "sentinel-2a",
                    },
                    "assets": {},
                }
            ],
            "context": {"returned": 1},
        },
    )
    session = Mock()
    session.post.return_value = token_response
    session.request.return_value = catalog_response
    client = CopernicusService(
        client_id="test-client-id",
        client_secret="test-client-secret",
        session=session,
    )

    result = client.search_sentinel2(
        start_date=date(2026, 10, 25),
        end_date=date(2026, 10, 25),
        latitude=10.5,
        longitude=20.5,
        limit=1,
    )

    token_call = session.post.call_args
    assert token_call.args[0] == TOKEN_URL
    assert token_call.kwargs["data"] == {
        "grant_type": "client_credentials",
        "client_id": "test-client-id",
        "client_secret": "test-client-secret",
    }
    assert token_call.kwargs["headers"]["Content-Type"] == "application/x-www-form-urlencoded"
    assert token_call.kwargs["timeout"] == (5.0, 90.0)
    catalog_call = session.request.call_args
    assert catalog_call.args == ("POST", CATALOG_SEARCH_URL)
    _assert_bearer_header(catalog_call, token_response.json.return_value["access_token"])
    assert catalog_call.kwargs["headers"]["Authorization"] == "Bearer mock-access-token"
    assert catalog_call.kwargs["headers"]["Accept"] == "application/geo+json"
    assert catalog_call.kwargs["json"]["collections"] == ["sentinel-2-l2a"]
    assert result["features"][0]["id"] == "sentinel-item-verified"
    assert result["features"][0]["acquisition_time"] == "2026-10-25T06:12:34Z"
    assert result["fetched_at"] != result["features"][0]["acquisition_time"]


def test_token_401_logs_only_sanitized_oauth_error(caplog) -> None:
    session = Mock()
    session.post.return_value = _response(
        401,
        {
            "error": "invalid_client",
            "error_description": "credential-value-must-not-be-logged",
            "access_token": "token-value-must-not-be-logged",
        },
    )
    client = CopernicusService(
        client_id="test-client-id",
        client_secret="credential-value-must-not-be-logged",
        session=session,
    )

    with caplog.at_level(logging.WARNING), pytest.raises(CopernicusAPIError):
        client.authenticate()

    assert "HTTP 401" in caplog.text
    assert "invalid_client" in caplog.text
    assert "credential-value-must-not-be-logged" not in caplog.text
    assert "token-value-must-not-be-logged" not in caplog.text
    assert "error_description" not in caplog.text


def test_catalog_401_refreshes_token_and_retries_with_bearer_header() -> None:
    session = Mock()
    session.post.side_effect = [
        _response(200, {"access_token": "first-mock-token", "expires_in": 3600}),
        _response(200, {"access_token": "refreshed-mock-token", "expires_in": 3600}),
    ]
    session.request.side_effect = [
        _response(401, {"error": "invalid_token"}),
        _response(200, {"features": [], "context": {}}),
    ]
    client = CopernicusService(
        client_id="test-client-id",
        client_secret="test-client-secret",
        session=session,
    )

    result = client.search_sentinel2(
        start_date=date(2026, 10, 25),
        end_date=date(2026, 10, 25),
        latitude=10.5,
        longitude=20.5,
        limit=1,
    )

    assert result["features"] == []
    assert session.post.call_count == 2
    assert session.request.call_count == 2
    authorization_headers = [
        call.kwargs["headers"]["Authorization"]
        for call in session.request.call_args_list
    ]
    assert len(authorization_headers) == 2
    _assert_bearer_header(session.request.call_args_list[0], "first-mock-token")
    _assert_bearer_header(session.request.call_args_list[1], "refreshed-mock-token")


def test_catalog_non_401_failure_does_not_refresh_or_expose_sensitive_values(caplog) -> None:
    access_token = "private-mock-access-token"
    client_secret = "private-mock-client-secret"
    session = Mock()
    session.post.return_value = _response(
        200,
        {"access_token": access_token, "expires_in": 3600},
    )
    session.request.return_value = _response(
        403,
        {
            "error": "access_denied",
            "access_token": access_token,
            "client_secret": client_secret,
        },
    )
    client = CopernicusService(
        client_id="test-client-id",
        client_secret=client_secret,
        session=session,
    )

    with caplog.at_level(logging.INFO), pytest.raises(CopernicusAPIError) as error:
        client.search_sentinel2(
            start_date=date(2026, 10, 25),
            end_date=date(2026, 10, 25),
            latitude=10.5,
            longitude=20.5,
            limit=1,
        )

    assert session.post.call_count == 1
    assert session.request.call_count == 1
    _assert_not_exposed(str(error.value), access_token, client_secret)
    _assert_not_exposed(caplog.text, access_token, client_secret)


def test_token_timeout_is_sanitized_and_reported(caplog) -> None:
    session = Mock()
    session.post.side_effect = Timeout("secret-must-not-appear")
    client = CopernicusService(
        client_id="test-client-id",
        client_secret="secret-must-not-appear",
        session=session,
    )

    with caplog.at_level(logging.WARNING), pytest.raises(CopernicusAPIError, match="authentication failed"):
        client.authenticate()

    assert "timeout" in caplog.text
    assert "secret-must-not-appear" not in caplog.text


@pytest.mark.parametrize(
    ("timeout_error", "error_label"),
    [
        (ConnectTimeout("credential-value-must-not-be-logged"), "connect_timeout"),
        (ReadTimeout("credential-value-must-not-be-logged"), "read_timeout"),
    ],
)
def test_process_api_reports_timeout_phase_without_sensitive_error_details(
    timeout_error, error_label: str, caplog
) -> None:
    session = Mock()
    session.post.return_value = _response(200, {"access_token": "private-token", "expires_in": 3600})
    session.request.side_effect = timeout_error
    client = CopernicusService(
        client_id="test-client",
        client_secret="credential-value-must-not-be-logged",
        connect_timeout_seconds=2.5,
        read_timeout_seconds=45,
        session=session,
    )

    with caplog.at_level(logging.WARNING), pytest.raises(CopernicusAPIError, match=error_label):
        client.get_satellite_image(
            collection="sentinel-2",
            latitude=10,
            longitude=20,
            start_date=date(2026, 10, 25),
            end_date=date(2026, 10, 26),
            width=64,
            height=64,
        )

    assert session.post.call_args.kwargs["timeout"] == (2.5, 45.0)
    assert session.request.call_args.kwargs["timeout"] == (2.5, 45.0)
    assert error_label.replace("_", " ") in caplog.text
    assert "credential-value-must-not-be-logged" not in caplog.text
    assert "private-token" not in caplog.text


def test_copernicus_timeout_values_load_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("COPERNICUS_CONNECT_TIMEOUT_SECONDS", "3.25")
    monkeypatch.setenv("COPERNICUS_READ_TIMEOUT_SECONDS", "55")
    session = Mock()
    session.post.return_value = _response(200, {"access_token": "private-token", "expires_in": 3600})
    client = CopernicusService(session=session)

    client.authenticate()

    assert session.post.call_args.kwargs["timeout"] == (3.25, 55.0)


@pytest.mark.parametrize("invalid", ["0", "-1", "nan", "inf", "not-a-number"])
def test_invalid_copernicus_timeout_configuration_is_rejected(monkeypatch, invalid: str) -> None:
    monkeypatch.setenv("COPERNICUS_READ_TIMEOUT_SECONDS", invalid)

    with pytest.raises(ValueError, match="COPERNICUS_READ_TIMEOUT_SECONDS"):
        CopernicusService()


@pytest.mark.parametrize("payload", [{}, {"access_token": ""}, {"access_token": 123}])
def test_malformed_successful_token_response_fails_closed(payload, caplog) -> None:
    session = Mock()
    session.post.return_value = _response(200, payload)
    client = CopernicusService(
        client_id="test-client-id",
        client_secret="test-client-secret",
        session=session,
    )

    with caplog.at_level(logging.WARNING), pytest.raises(CopernicusAPIError, match="did not contain an access token"):
        client.authenticate()

    assert "valid access token" in caplog.text
    assert "test-client-secret" not in caplog.text


def test_authentication_fails_clearly_when_environment_credentials_are_unavailable(monkeypatch, caplog) -> None:
    monkeypatch.delenv("COPERNICUS_CLIENT_ID", raising=False)
    monkeypatch.delenv("COPERNICUS_CLIENT_SECRET", raising=False)
    client = CopernicusService()

    with caplog.at_level(logging.WARNING), pytest.raises(CopernicusConfigurationError, match="not configured"):
        client.authenticate()

    assert "credentials are unset" in caplog.text
    assert "access token" not in caplog.text


def test_catalog_response_separates_scene_acquisition_from_fetch_time(monkeypatch) -> None:
    monkeypatch.setattr(
        satellite.copernicus_service,
        "search_sentinel2",
        lambda **_: {
            "collection": "sentinel-2-l2a",
            "fetched_at": "2026-11-12T08:30:00Z",
            "features": [
                {
                    "id": "scene-123",
                    "collection": "sentinel-2-l2a",
                    "sensing_time": "2026-11-10T05:42:11Z",
                    "acquisition_time": "2026-11-10T05:42:11Z",
                    "cloud_coverage": 18.5,
                    "platform": "sentinel-2b",
                    "instruments": ["MSI"],
                    "bbox": [10, 20, 11, 21],
                    "assets": {},
                }
            ],
            "context": {},
            "query": {},
        },
    )

    with _client() as client:
        response = client.get(
            "/api/satellite/search/sentinel-2",
            params={
                "start_date": "2026-11-01",
                "end_date": "2026-11-12",
                "latitude": -33.8688,
                "longitude": 151.2093,
            },
        )

    assert response.status_code == 200
    result = response.json()
    feature = result["features"][0]
    assert result["fetched_at"] == "2026-11-12T08:30:00Z"
    assert result["catalog_search_status"] == "COMPLETED"
    assert result["catalog_results_status"] == "RESULTS_FOUND"
    assert result["imagery_status"] == "NOT_REQUESTED"
    assert feature["acquisition_time"] == "2026-11-10T05:42:11Z"
    assert feature["sensing_time"] == feature["acquisition_time"]
    assert feature["canonical_record"]["contract_version"] == "1.0"
    assert feature["canonical_record"]["record_type"] == "satellite_acquisition"
    assert feature["canonical_record"]["quality_status"] == "UNVERIFIED"
    assert feature["canonical_record"]["timestamps"]["acquisition_time_utc"] == "2026-11-10T05:42:11Z"
    assert feature["canonical_record"]["timestamps"]["retrieval_time_utc"] == "2026-11-12T08:30:00Z"
    assert feature["provenance"] == {
        "provider": "Copernicus Data Space",
        "product": "sentinel-2-l2a",
        "source_record_id": "scene-123",
        "location": {
            "name": None,
            "latitude": -33.8688,
            "longitude": 151.2093,
            "station_id": None,
            "station_id_is_internal": None,
            "region": None,
            "country": None,
        },
        "observation_time": "2026-11-10T05:42:11Z",
        "fetched_at": "2026-11-12T08:30:00Z",
        "units": {"cloud_coverage": "%"},
        "freshness_status": "UNVERIFIED",
        "provider_metadata": {
            "acquisition_time_raw": "2026-11-10T05:42:11Z",
            "platform": "sentinel-2b",
            "instruments": ["MSI"],
            "cloud_coverage": 18.5,
            "bbox": [10, 20, 11, 21],
        },
    }


def test_catalog_response_retains_missing_or_malformed_acquisition_as_unverified(monkeypatch) -> None:
    monkeypatch.setattr(
        satellite.copernicus_service,
        "search_sentinel1",
        lambda **_: {
            "collection": "sentinel-1-grd",
            "fetched_at": "2026-11-12T08:30:00Z",
            "features": [
                {"id": "scene-missing", "collection": "sentinel-1-grd"},
                {
                    "id": "scene-invalid",
                    "collection": "sentinel-1-grd",
                    "sensing_time": "not-a-timestamp",
                },
            ],
            "context": {},
            "query": {},
        },
    )

    with _client() as client:
        response = client.get(
            "/api/satellite/search/sentinel-1",
            params={"start_date": "2026-11-01", "end_date": "2026-11-12", "latitude": 0, "longitude": 0},
        )

    assert response.status_code == 200
    features = response.json()["features"]
    assert features[0]["provenance"]["observation_time"] is None
    assert features[0]["provenance"]["freshness_status"] == "UNVERIFIED"
    assert features[1]["provenance"]["observation_time"] is None
    assert features[1]["provenance"]["provider_metadata"]["acquisition_time_raw"] == "not-a-timestamp"


@pytest.mark.parametrize(
    ("features", "result_status"),
    [([], "NO_RESULTS"), ([{"id": "scene"}], "RESULTS_FOUND")],
)
def test_catalog_response_distinguishes_search_results_from_imagery(
    monkeypatch, features, result_status
) -> None:
    monkeypatch.setattr(
        satellite.copernicus_service,
        "search_sentinel2",
        lambda **_: {
            "collection": "sentinel-2-l2a",
            "fetched_at": "2026-11-12T08:30:00Z",
            "features": features,
            "context": {},
            "query": {},
        },
    )

    with _client() as client:
        response = client.get(
            "/api/satellite/search/sentinel-2",
            params={"start_date": "2026-11-01", "end_date": "2026-11-12", "latitude": 10, "longitude": 20},
        )

    assert response.status_code == 200
    result = response.json()
    assert result["catalog_search_status"] == "COMPLETED"
    assert result["catalog_results_status"] == result_status
    assert result["imagery_status"] == "NOT_REQUESTED"


def test_satellite_status_only_reports_authentication_and_leaves_catalog_and_imagery_unchecked(monkeypatch) -> None:
    monkeypatch.setattr(satellite.copernicus_service, "authenticate", lambda: "private-token")

    with _client() as client:
        response = client.get("/api/satellite/status")

    assert response.status_code == 200
    assert response.json() == {
        "service": "Copernicus",
        "authenticated": True,
        "authentication_status": "AUTHENTICATED",
        "catalog_search_status": "NOT_CHECKED",
        "catalog_results_status": "NOT_CHECKED",
        "imagery_status": "NOT_CHECKED",
        "details": "OAuth succeeded; Catalog availability, scene results, and image retrieval were not checked.",
    }
    assert "sentinel1" not in response.json()
    assert "sentinel2" not in response.json()


def test_process_api_image_identifies_request_time_without_claiming_acquisition_time(monkeypatch) -> None:
    monkeypatch.setattr(satellite.copernicus_service, "get_satellite_image", lambda **_: b"tiff")

    with _client() as client:
        response = client.get(
            "/api/satellite/image/sentinel-1",
            params={
                "start_date": "2026-11-01",
                "end_date": "2026-11-12",
                "latitude": -33.8688,
                "longitude": 151.2093,
            },
        )

    assert response.status_code == 200
    assert response.content == b"tiff"
    assert response.headers["x-data-provider"] == "Copernicus Data Space"
    assert response.headers["x-acquisition-time"] == "UNRESOLVED"
    assert response.headers["x-requested-time-range"] == "2026-11-01/2026-11-12"
    assert "does not identify a single source-scene acquisition time" in response.headers["x-imagery-time-limitation"]
    assert response.headers["x-request-time"].endswith("Z")


def test_process_api_returns_only_bounded_geotiff_for_global_bbox() -> None:
    process_response = Mock(spec=Response)
    process_response.ok = True
    process_response.status_code = 200
    process_response.headers = {"Content-Type": "image/tiff"}
    process_response.content = _geotiff(256, 128)
    process_response.iter_content.return_value = iter([process_response.content])
    session = Mock()
    session.post.return_value = _response(
        200,
        {"access_token": "mock-process-token", "expires_in": 3600},
    )
    session.request.return_value = process_response
    client = CopernicusService(client_id="test-id", client_secret="test-secret", session=session)

    image = client.get_satellite_image(
        collection="sentinel-2",
        bbox=(-122.42, 37.77, -122.40, 37.79),
        start_date=date(2026, 10, 25),
        end_date=date(2026, 10, 26),
        width=256,
        height=128,
    )

    assert image == _geotiff(256, 128)
    request = session.request.call_args
    assert request.args == ("POST", PROCESS_URL)
    assert session.post.call_count == 1
    _assert_bearer_header(request, "mock-process-token")
    body = request.kwargs["json"]
    assert body["input"]["bounds"]["bbox"] == [-122.42, 37.77, -122.4, 37.79]
    assert body["input"]["data"][0]["type"] == "sentinel-2-l2a"
    assert body["output"]["width"] == 256
    assert body["output"]["height"] == 128
    assert body["output"]["responses"][0]["format"]["type"] == "image/tiff"


def test_process_api_rejects_large_or_invalid_bounding_boxes_before_request() -> None:
    session = Mock()
    client = CopernicusService(client_id="test-id", client_secret="test-secret", session=session)

    with pytest.raises(ValueError, match="at most 0.25 degrees"):
        client.get_satellite_image(
            collection="sentinel-2",
            bbox=(-1, 0, 1, 0.1),
            start_date=date(2026, 10, 25),
            end_date=date(2026, 10, 26),
        )
    with pytest.raises(ValueError, match="latitude must be between -90 and 90"):
        client.get_satellite_image(
            collection="sentinel-2",
            latitude=91,
            longitude=0,
            start_date=date(2026, 10, 25),
            end_date=date(2026, 10, 26),
        )
    session.request.assert_not_called()


@pytest.mark.parametrize(
    ("content_type", "content", "message"),
    [
        ("application/json", b'{"error":"not-an-image"}', "did not return a GeoTIFF"),
        ("image/tiff", b"", "empty image"),
    ],
)
def test_process_api_rejects_non_geotiff_or_empty_response(
    content_type: str, content: bytes, message: str
) -> None:
    process_response = Mock(spec=Response)
    process_response.ok = True
    process_response.status_code = 200
    process_response.headers = {"Content-Type": content_type}
    process_response.content = content
    process_response.iter_content.return_value = iter([content])
    session = Mock()
    session.request.return_value = process_response
    client = CopernicusService(client_id="test-id", client_secret="test-secret", session=session)
    client.authenticate = lambda force_refresh=False: "mock-token"

    with pytest.raises(CopernicusAPIError, match=message):
        client.get_satellite_image(
            collection="sentinel-2",
            latitude=10,
            longitude=20,
            start_date=date(2026, 10, 25),
            end_date=date(2026, 10, 26),
        )


@pytest.mark.parametrize(
    ("headers", "content", "message"),
    [
        pytest.param(
            {"Content-Type": "image/tiff", "Content-Length": str(MAX_IMAGE_RESPONSE_BYTES + 1)},
            b"tiff",
            "size limit",
            id="declared-size-exceeds-limit",
        ),
        pytest.param(
            {"Content-Type": "image/tiff", "Content-Length": "not-a-number"},
            b"tiff",
            "invalid image length",
            id="invalid-content-length",
        ),
        pytest.param(
            {"Content-Type": "image/tiff"},
            b"x" * (MAX_IMAGE_RESPONSE_BYTES + 1),
            "size limit",
            id="streamed-body-exceeds-limit",
        ),
    ],
)
def test_process_api_rejects_oversized_or_invalid_length_responses(
    headers: dict[str, str], content: bytes, message: str
) -> None:
    process_response = Mock(spec=Response)
    process_response.ok = True
    process_response.status_code = 200
    process_response.headers = headers
    process_response.content = content
    process_response.iter_content.return_value = iter([content])
    session = Mock()
    session.request.return_value = process_response
    client = CopernicusService(client_id="test-id", client_secret="test-secret", session=session)
    client.authenticate = lambda force_refresh=False: "mock-token"

    with pytest.raises(CopernicusAPIError, match=message):
        client.get_satellite_image(
            collection="sentinel-2",
            latitude=10,
            longitude=20,
            start_date=date(2026, 10, 25),
            end_date=date(2026, 10, 26),
        )


def test_process_api_stream_read_timeout_is_reported_as_read_timeout() -> None:
    process_response = Mock(spec=Response)
    process_response.ok = True
    process_response.status_code = 200
    process_response.headers = {"Content-Type": "image/tiff"}
    process_response.iter_content.side_effect = ReadTimeout("sensitive provider detail")
    session = Mock()
    session.request.return_value = process_response
    client = CopernicusService(client_id="test-id", client_secret="test-secret", session=session)
    client.authenticate = lambda force_refresh=False: "mock-token"

    with pytest.raises(CopernicusAPIError, match="read_timeout"):
        client.get_satellite_image(
            collection="sentinel-2",
            latitude=10,
            longitude=20,
            start_date=date(2026, 10, 25),
            end_date=date(2026, 10, 26),
            width=64,
            height=64,
        )

    assert process_response.close.called
    assert "sensitive provider detail" not in str(session.request.call_args)


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [(19.076, 72.8777), (-1.2921, 36.8219), (-23.5505, -46.6333), (-33.8688, 151.2093)],
)
def test_process_api_accepts_global_coordinates_with_mocked_provider(
    monkeypatch, latitude: float, longitude: float
) -> None:
    process_response = Mock(spec=Response)
    process_response.ok = True
    process_response.status_code = 200
    process_response.headers = {"Content-Type": "image/tiff"}
    process_response.content = _geotiff(512, 512)
    process_response.iter_content.return_value = iter([process_response.content])
    session = Mock()
    session.request.return_value = process_response
    client = CopernicusService(client_id="test-id", client_secret="test-secret", session=session)
    monkeypatch.setattr(client, "authenticate", lambda force_refresh=False: "mock-token")

    client.get_satellite_image(
        collection="sentinel-2",
        latitude=latitude,
        longitude=longitude,
        start_date=date(2026, 10, 25),
        end_date=date(2026, 10, 26),
    )

    bbox = session.request.call_args.kwargs["json"]["input"]["bounds"]["bbox"]
    assert bbox[0] <= longitude <= bbox[2]
    assert bbox[1] <= latitude <= bbox[3]


def test_process_api_provider_forbidden_and_timeout_are_reported_safely() -> None:
    token_response = _response(200, {"access_token": "mock-access-token", "expires_in": 3600})
    forbidden_response = _response(403, {"error": "access_denied"})
    forbidden_session = Mock()
    forbidden_session.post.return_value = token_response
    forbidden_session.request.return_value = forbidden_response
    forbidden_client = CopernicusService(
        client_id="test-id",
        client_secret="test-secret",
        session=forbidden_session,
    )

    with pytest.raises(CopernicusAPIError, match="permissions"):
        forbidden_client.get_satellite_image(
            collection="sentinel-2",
            latitude=10,
            longitude=20,
            start_date=date(2026, 10, 25),
            end_date=date(2026, 10, 26),
        )

    timeout_session = Mock()
    timeout_session.post.return_value = token_response
    timeout_session.request.side_effect = Timeout("provider-internal-detail")
    timeout_client = CopernicusService(
        client_id="test-id",
        client_secret="test-secret",
        session=timeout_session,
    )
    with pytest.raises(CopernicusAPIError, match="network or timeout"):
        timeout_client.get_satellite_image(
            collection="sentinel-2",
            latitude=10,
            longitude=20,
            start_date=date(2026, 10, 25),
            end_date=date(2026, 10, 26),
        )


def test_retrieve_sentinel2_scene_uses_valid_catalog_scene_and_preserves_provenance(monkeypatch) -> None:
    client = CopernicusService(client_id="test-id", client_secret="test-secret")
    client.search_sentinel2 = lambda **_: {
        "collection": "sentinel-2-l2a",
        "fetched_at": "2026-11-12T08:30:00Z",
        "features": [
            {
                "id": "cloudy-scene",
                "acquisition_time": "2026-11-10T05:42:11Z",
                "cloud_coverage": 50,
                "bbox": [20, 10, 21, 11],
            },
            {
                "id": "clearer-scene",
                "acquisition_time": "2026-11-09T05:42:11Z",
                "cloud_coverage": 10,
                "bbox": [20, 10, 21, 11],
            },
        ],
    }
    process_calls = []

    def fake_process(**kwargs):
        process_calls.append(kwargs)
        return b"mock-geotiff"

    monkeypatch.setattr(client, "get_satellite_image", fake_process)
    result = client.retrieve_sentinel2_scene(
        start_date=date(2026, 11, 1),
        end_date=date(2026, 11, 12),
        latitude=10.5,
        longitude=20.5,
        cloud_coverage=30,
        width=256,
        height=256,
    )

    assert result["image"] == b"mock-geotiff"
    assert result["catalog_item_id"] == "clearer-scene"
    assert result["collection"] == "sentinel-2-l2a"
    assert result["acquisition_time"] == datetime(2026, 11, 9, 5, 42, 11, tzinfo=timezone.utc)
    assert result["catalog_fetched_at"] == "2026-11-12T08:30:00Z"
    assert result["process_requested_at"] <= result["downloaded_at"]
    assert result["requested_bbox"] == [20.49, 10.49, 20.51, 10.51]
    assert result["cloud_coverage"] == 10
    assert result["processing_parameters"]["bands"] == ["B04", "B03", "B02"]
    assert result["processing_parameters"]["sample_type"] == "UINT16"
    assert result["provenance"]["scene_match_status"] == "TIME_AND_AOI_MATCHED_NOT_ITEM_PINNED"
    assert result["canonical_record"]["record_type"] == "satellite_acquisition"
    assert result["canonical_record"]["quality_status"] == "UNVERIFIED"
    assert result["canonical_record"]["payload"]["process_result_pinned_to_catalog_item"] is False
    assert result["canonical_record"]["timestamps"]["acquisition_time_utc"] == "2026-11-09T05:42:11Z"
    assert result["canonical_record"]["timestamps"]["retrieval_time_utc"] == result["downloaded_at"].isoformat().replace("+00:00", "Z")
    assert process_calls[0]["start_date"] == result["acquisition_time"]
    assert process_calls[0]["end_date"] > result["acquisition_time"]


def test_retrieve_sentinel2_scene_reports_no_usable_catalog_scenes() -> None:
    client = CopernicusService(client_id="test-id", client_secret="test-secret")
    client.search_sentinel2 = lambda **_: {"fetched_at": "2026-11-12T08:30:00Z", "features": []}

    with pytest.raises(CopernicusSceneNotFoundError, match="No Sentinel-2 Catalog scene"):
        client.retrieve_sentinel2_scene(
            start_date=date(2026, 11, 1),
            end_date=date(2026, 11, 12),
            latitude=-33.8688,
            longitude=151.2093,
        )


def test_sentinel2_scene_route_returns_geo_tiff_and_metadata_headers(monkeypatch) -> None:
    monkeypatch.setattr(
        satellite.copernicus_service,
        "retrieve_sentinel2_scene",
        lambda **_: {
            "image": _geotiff(256, 128),
            "catalog_item_id": "scene/with-id",
            "width": 256,
            "height": 128,
            "format": "image/tiff",
            "processing_parameters": {
                "bands": ["B04", "B03", "B02"],
                "sample_type": "UINT16",
            },
            "provenance": {
                "provider": "Copernicus Data Space",
                "product": "sentinel-2-l2a",
                "source_record_id": "scene/with-id",
                "acquisition_time": "2026-11-10T05:42:11Z",
                "catalog_fetched_at": "2026-11-12T08:30:00Z",
                "process_requested_at": "2026-11-12T08:31:00Z",
                "downloaded_at": "2026-11-12T08:31:03Z",
                "requested_bbox": [-122.42, 37.77, -122.4, 37.79],
                "catalog_item_bbox": [-123, 37, -122, 38],
                "cloud_coverage": 17,
                "freshness_status": "UNVERIFIED",
                "scene_match_status": "TIME_AND_AOI_MATCHED_NOT_ITEM_PINNED",
            },
        },
    )

    with _client() as client:
        response = client.get(
            "/api/satellite/scene/sentinel-2",
            params={
                "start_date": "2026-11-01",
                "end_date": "2026-11-12",
                "west": -122.42,
                "south": 37.77,
                "east": -122.4,
                "north": 37.79,
                "width": 256,
                "height": 128,
            },
        )

    assert response.status_code == 200
    assert response.content == _geotiff(256, 128)
    assert response.headers["content-type"].startswith("image/tiff")
    assert response.headers["x-catalog-item-id"] == "scene%2Fwith-id"
    assert response.headers["x-acquisition-time"] == "2026-11-10T05:42:11Z"
    metadata = json.loads(unquote(response.headers["x-satellite-metadata"]))
    assert metadata["source_record_id"] == "scene/with-id"
    assert metadata["catalog_fetched_at"] == "2026-11-12T08:30:00Z"
    assert metadata["process_requested_at"] == "2026-11-12T08:31:00Z"
    assert metadata["downloaded_at"] == "2026-11-12T08:31:03Z"
    if "canonical_record" in metadata:
        assert metadata["canonical_record"]["record_type"] == "satellite_acquisition"
        assert metadata["canonical_record"]["quality_status"] == "UNVERIFIED"
        assert metadata["canonical_record"]["payload"]["process_result_pinned_to_catalog_item"] is False
    assert metadata["catalog_search_status"] == "COMPLETED"
    assert metadata["catalog_results_status"] == "RESULTS_FOUND"
    assert metadata["imagery_status"] == "RETRIEVED"
    assert metadata["width"] == 256
    assert metadata["height"] == 128


def test_sentinel2_scene_route_rejects_invalid_tiff_response(monkeypatch) -> None:
    monkeypatch.setattr(
        satellite.copernicus_service,
        "retrieve_sentinel2_scene",
        lambda **_: {
            "image": b"not-a-tiff",
            "catalog_item_id": "scene-id",
            "width": 64,
            "height": 64,
            "format": "image/tiff",
            "processing_parameters": {},
            "provenance": {
                "provider": "Copernicus Data Space",
                "product": "sentinel-2-l2a",
                "source_record_id": "scene-id",
                "acquisition_time": "2026-11-10T05:42:11Z",
                "catalog_fetched_at": "2026-11-12T08:30:00Z",
                "process_requested_at": "2026-11-12T08:31:00Z",
                "downloaded_at": "2026-11-12T08:31:03Z",
                "requested_bbox": [-122.42, 37.77, -122.4, 37.79],
                "cloud_coverage": None,
                "freshness_status": "UNVERIFIED",
                "scene_match_status": "TIME_AND_AOI_MATCHED_NOT_ITEM_PINNED",
            },
        },
    )
    with _client() as client:
        response = client.get(
            "/api/satellite/scene/sentinel-2",
            params={
                "start_date": "2026-11-01",
                "end_date": "2026-11-12",
                "latitude": 10,
                "longitude": 20,
                "width": 64,
                "height": 64,
            },
        )
    assert response.status_code == 502
    assert response.json()["detail"] == "Copernicus Process API returned an invalid GeoTIFF image."


def test_sentinel2_scene_route_rejects_missing_or_ambiguous_location(monkeypatch) -> None:
    service = Mock()
    monkeypatch.setattr(satellite, "copernicus_service", service)
    with _client() as client:
        missing = client.get(
            "/api/satellite/scene/sentinel-2",
            params={"start_date": "2026-11-01", "end_date": "2026-11-12"},
        )
        ambiguous = client.get(
            "/api/satellite/scene/sentinel-2",
            params={
                "start_date": "2026-11-01",
                "end_date": "2026-11-12",
                "latitude": 10,
                "longitude": 20,
                "west": 19,
                "south": 9,
                "east": 21,
                "north": 11,
            },
        )

    assert missing.status_code == 422
    assert ambiguous.status_code == 422
    service.retrieve_sentinel2_scene.assert_not_called()


def test_sentinel2_scene_route_requires_authentication() -> None:
    application = FastAPI()
    application.include_router(satellite.router, prefix="/api")
    with TestClient(application) as client:
        response = client.get(
            "/api/satellite/scene/sentinel-2",
            params={
                "start_date": "2026-11-01",
                "end_date": "2026-11-12",
                "latitude": 10,
                "longitude": 20,
            },
        )
    assert response.status_code == 401


def test_sentinel2_scene_route_maps_no_scene_to_not_found(monkeypatch) -> None:
    def no_scene(**_):
        raise CopernicusSceneNotFoundError("No matching scene.")

    monkeypatch.setattr(satellite.copernicus_service, "retrieve_sentinel2_scene", no_scene)

    with _client() as client:
        response = client.get(
            "/api/satellite/scene/sentinel-2",
            params={
                "start_date": "2026-11-01",
                "end_date": "2026-11-12",
                "latitude": 10,
                "longitude": 20,
            },
        )

    assert response.status_code == 404
    assert "No matching scene" in response.json()["detail"]


def test_catalog_adapter_preserves_provider_scene_metadata(monkeypatch) -> None:
    response = Mock(spec=Response)
    response.ok = True
    response.status_code = 200
    response.json.return_value = {
        "features": [
            {
                "id": "sentinel-item-42",
                "collection": "sentinel-2-l2a",
                "properties": {
                    "datetime": "2026-10-25T06:12:34Z",
                    "eo:cloud_cover": 27.0,
                    "platform": "sentinel-2a",
                    "instruments": ["MSI"],
                },
                "assets": {"visual": {"title": "Visual", "type": "image/tiff", "href": "not-returned"}},
                "bbox": [20, 10, 21, 11],
                "geometry": {"type": "Point", "coordinates": [20.5, 10.5]},
            }
        ],
        "context": {"returned": 1},
    }
    session = Mock()
    session.request.return_value = response
    client = CopernicusService(client_id="test-id", client_secret="test-secret", session=session)
    monkeypatch.setattr(client, "authenticate", lambda force_refresh=False: "mock-token")

    result = client.search_sentinel2(
        start_date=date(2026, 10, 25),
        end_date=date(2026, 10, 25),
        latitude=10.5,
        longitude=20.5,
    )

    feature = result["features"][0]
    assert result["fetched_at"].endswith("Z")
    assert feature["id"] == "sentinel-item-42"
    assert feature["acquisition_time"] == "2026-10-25T06:12:34Z"
    assert feature["sensing_time"] == feature["acquisition_time"]
    assert feature["cloud_coverage"] == 27.0
    assert feature["platform"] == "sentinel-2a"
    assert feature["instruments"] == ["MSI"]
    assert feature["assets"] == {"visual": {"title": "Visual", "type": "image/tiff"}}
    assert session.request.call_args.kwargs["json"]["bbox"] == [20.49, 10.49, 20.51, 10.51]
