from datetime import date
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock

import pytest
from PIL import Image, TiffImagePlugin
from requests.exceptions import ConnectTimeout, ReadTimeout

from app.services.copernicus_service import CATALOG_SEARCH_URL, PROCESS_URL, TOKEN_URL
from scripts.copernicus_process_diagnostic import run_diagnostic


def _response(
    status_code: int,
    *,
    payload: object = None,
    content: bytes = b"",
    content_type: str = "application/json",
) -> Mock:
    response = Mock()
    response.status_code = status_code
    response.ok = 200 <= status_code < 400
    response.headers = {"Content-Type": content_type}
    response.content = content
    response.iter_content.return_value = iter([content])
    response.json.return_value = payload
    return response


def _valid_tiff(width: int = 128, height: int = 128) -> bytes:
    buffer = BytesIO()
    tags = TiffImagePlugin.ImageFileDirectory_v2()
    tags[33550] = (0.0001, 0.0001, 0.0)
    tags[33922] = (0.0, 0.0, 0.0, 20.0, 10.0, 0.0)
    tags[34735] = (1, 1, 0, 1)
    Image.new("RGB", (width, height), color=(1, 2, 3)).save(
        buffer,
        format="TIFF",
        tiffinfo=tags,
    )
    return buffer.getvalue()


def _plain_tiff(width: int = 128, height: int = 128) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (width, height)).save(buffer, format="TIFF")
    return buffer.getvalue()


def _feature() -> dict:
    return {
        "id": "sentinel-item-42",
        "collection": "sentinel-2-l2a",
        "properties": {
            "datetime": "2026-11-05T05:42:11Z",
            "eo:cloud_cover": 12.0,
        },
        "bbox": [20.0, 10.0, 21.0, 11.0],
        "assets": {},
    }


def _session_responses(process_response: Mock, catalog_response: Mock | None = None) -> Mock:
    session = Mock()
    session.request.side_effect = [
        _response(200, payload={"access_token": "private-token", "expires_in": 3600}),
        catalog_response or _response(200, payload={"features": [_feature()], "context": {}}),
        process_response,
    ]
    return session


def _run(session: Mock, tmp_path: Path, output: list[str], **overrides) -> int:
    values = {
        "latitude": 10.5,
        "longitude": 20.5,
        "start_date": date(2026, 11, 1),
        "end_date": date(2026, 11, 12),
        "session": session,
        "environment": {
            "COPERNICUS_CLIENT_ID": "local-test-client",
            "COPERNICUS_CLIENT_SECRET": "local-test-secret",
        },
        "output_dir": tmp_path,
        "output": output.append,
    }
    values.update(overrides)
    return run_diagnostic(**values)


def test_process_diagnostic_reports_and_saves_valid_bounded_geotiff(tmp_path) -> None:
    session = _session_responses(
        _response(
            200,
            content=_valid_tiff(),
            content_type="image/tiff",
        )
    )
    output: list[str] = []

    status = _run(session, tmp_path, output)

    transcript = "\n".join(output)
    assert status == 0
    assert "OAuth HTTP status: 200" in output
    assert "OAuth succeeded: yes" in output
    assert "Catalog HTTP status: 200" in output
    assert "Catalog features returned: 1" in output
    assert "Catalog item ID: sentinel-item-42" in output
    assert "Acquisition time: 2026-11-05T05:42:11Z" in output
    assert any(line.startswith("Process request time: ") for line in output)
    assert any(line.startswith("Image response received at: ") for line in output)
    assert "Process API HTTP status: 200" in output
    assert "Process API content type: image/tiff" in output
    assert "Valid GeoTIFF received: yes" in output
    assert "GeoTIFF dimensions: 128x128" in output
    assert "Imagery tied to selected Catalog item: no" in output
    assert "local-test-secret" not in transcript
    assert "private-token" not in transcript
    assert "Authorization" not in transcript
    saved_files = list(tmp_path.glob("sentinel-2-process-test-*.tiff"))
    assert len(saved_files) == 1
    assert saved_files[0].read_bytes() == _valid_tiff()
    assert session.request.call_count == 3
    assert [call.args[1] for call in session.request.call_args_list] == [
        TOKEN_URL,
        CATALOG_SEARCH_URL,
        PROCESS_URL,
    ]
    catalog_body = session.request.call_args_list[1].kwargs["json"]
    assert catalog_body["collections"] == ["sentinel-2-l2a"]
    assert catalog_body["limit"] == 5
    process_body = session.request.call_args_list[2].kwargs["json"]
    assert process_body["input"]["data"][0]["type"] == "sentinel-2-l2a"
    assert process_body["input"]["bounds"]["bbox"] == [20.49, 10.49, 20.51, 10.51]
    assert process_body["output"]["width"] == 128
    assert process_body["output"]["height"] == 128
    assert process_body["output"]["responses"][0]["format"]["type"] == "image/tiff"
    assert "B04" in process_body["evalscript"]
    assert "B03" in process_body["evalscript"]
    assert "B02" in process_body["evalscript"]
    assert process_body["input"]["data"][0]["dataFilter"]["timeRange"]["from"] == (
        "2026-11-05T05:42:11Z"
    )
    assert process_body["input"]["data"][0]["dataFilter"]["timeRange"]["to"] == (
        "2026-11-05T05:42:12Z"
    )


def test_missing_credentials_do_not_make_requests(tmp_path) -> None:
    session = Mock()
    output: list[str] = []

    status = run_diagnostic(
        latitude=10,
        longitude=20,
        session=session,
        environment={},
        output_dir=tmp_path,
        output=output.append,
    )

    assert status == 2
    assert "OAuth succeeded: no (credentials unavailable; no external request made)" in output
    session.request.assert_not_called()


def test_oauth_401_is_reported_without_catalog_or_process_request(tmp_path) -> None:
    session = Mock()
    session.request.return_value = _response(401, payload={"error": "invalid_client"})
    output: list[str] = []

    status = _run(session, tmp_path, output)

    assert status == 3
    assert "OAuth HTTP status: 401" in output
    assert "OAuth error code: invalid_client" in output
    assert "Catalog search succeeded: no (not attempted)" in output
    assert session.request.call_count == 1


def test_malformed_successful_oauth_response_stops_before_catalog(tmp_path) -> None:
    session = Mock()
    session.request.return_value = _response(200, payload={"expires_in": 300})
    output: list[str] = []

    status = _run(session, tmp_path, output)

    assert status == 3
    assert "OAuth HTTP status: 200" in output
    assert "OAuth error code: malformed_response" in output
    assert "Catalog search succeeded: no (not attempted)" in output
    assert session.request.call_count == 1


@pytest.mark.parametrize(("catalog_status", "expected_error"), [(401, "unauthorized"), (403, "forbidden")])
def test_catalog_authorization_failures_are_reported_separately(
    tmp_path, catalog_status: int, expected_error: str
) -> None:
    session = _session_responses(
        _response(200, content=_valid_tiff(), content_type="image/tiff"),
        catalog_response=_response(catalog_status, payload={"error": expected_error}),
    )
    output: list[str] = []

    status = _run(session, tmp_path, output)

    assert status == 4
    assert "OAuth succeeded: yes" in output
    assert f"Catalog HTTP status: {catalog_status}" in output
    assert f"Catalog error code: {expected_error}" in output
    assert "Process API request succeeded: no (not attempted)" in output
    assert session.request.call_count == 2


def test_empty_catalog_result_does_not_call_process_api(tmp_path) -> None:
    session = _session_responses(
        _response(200, content=_valid_tiff(), content_type="image/tiff"),
        catalog_response=_response(200, payload={"features": [], "context": {}}),
    )
    output: list[str] = []

    status = _run(session, tmp_path, output)

    assert status == 5
    assert "Catalog features returned: 0" in output
    assert "Process API request succeeded: no (no usable scene found)" in output
    assert session.request.call_count == 2


def test_catalog_timeout_is_reported_without_process_request(tmp_path) -> None:
    session = Mock()
    session.request.side_effect = [
        _response(200, payload={"access_token": "private-token", "expires_in": 3600}),
        ReadTimeout("private-token and sensitive body"),
    ]
    output: list[str] = []

    status = _run(session, tmp_path, output)

    assert status == 4
    assert "OAuth succeeded: yes" in output
    assert "Catalog HTTP status: unavailable" in output
    assert "Catalog error code: read_timeout" in output
    assert "Process API request succeeded: no (not attempted)" in output
    assert "private-token" not in "\n".join(output)


@pytest.mark.parametrize(
    ("process_status", "expected_error"),
    [(401, "unauthorized"), (403, "forbidden")],
)
def test_process_api_authorization_failure_does_not_retry_in_diagnostic(
    tmp_path, process_status: int, expected_error: str
) -> None:
    session = _session_responses(
        _response(process_status, payload={"error": expected_error}),
    )
    output: list[str] = []

    status = _run(session, tmp_path, output)

    assert status == 6
    assert f"Process API HTTP status: {process_status}" in output
    assert f"Process API error code: {expected_error}" in output
    assert "Valid GeoTIFF received: no" in output
    assert session.request.call_count == 3


def test_process_timeout_is_sanitized_and_reported(tmp_path) -> None:
    session = Mock()
    session.request.side_effect = [
        _response(200, payload={"access_token": "private-token", "expires_in": 3600}),
        _response(200, payload={"features": [_feature()], "context": {}}),
        ReadTimeout("private-token and sensitive body"),
    ]
    output: list[str] = []

    status = _run(session, tmp_path, output)

    assert status == 6
    assert "Process API HTTP status: unavailable" in output
    assert "Process API error code: read_timeout" in output
    assert "private-token" not in "\n".join(output)
    assert "sensitive body" not in "\n".join(output)


def test_process_connect_timeout_is_distinguished_from_read_timeout(tmp_path) -> None:
    session = Mock()
    session.request.side_effect = [
        _response(200, payload={"access_token": "private-token", "expires_in": 3600}),
        _response(200, payload={"features": [_feature()], "context": {}}),
        ConnectTimeout("private-token and sensitive body"),
    ]
    output: list[str] = []

    status = _run(session, tmp_path, output)

    assert status == 6
    assert "Process API error code: connect_timeout" in output
    assert "private-token" not in "\n".join(output)


def test_timeout_settings_are_configurable_and_reported(tmp_path) -> None:
    session = _session_responses(_response(200, content=_valid_tiff(), content_type="image/tiff"))
    output: list[str] = []

    status = _run(
        session,
        tmp_path,
        output,
        connect_timeout_seconds=3.5,
        read_timeout_seconds=45,
    )

    assert status == 0
    assert "Connect timeout seconds: 3.5" in output
    assert "Read timeout seconds: 45" in output
    assert session.request.call_args_list[0].kwargs["timeout"] == (3.5, 45.0)
    assert session.request.call_args_list[2].kwargs["timeout"] == (3.5, 45.0)


def test_timeout_settings_can_be_loaded_from_environment(tmp_path) -> None:
    session = _session_responses(_response(200, content=_valid_tiff(), content_type="image/tiff"))
    output: list[str] = []

    status = _run(
        session,
        tmp_path,
        output,
        environment={
            "COPERNICUS_CLIENT_ID": "local-test-client",
            "COPERNICUS_CLIENT_SECRET": "local-test-secret",
            "COPERNICUS_CONNECT_TIMEOUT_SECONDS": "4",
            "COPERNICUS_READ_TIMEOUT_SECONDS": "75",
        },
    )

    assert status == 0
    assert "Connect timeout seconds: 4" in output
    assert "Read timeout seconds: 75" in output
    assert session.request.call_args_list[0].kwargs["timeout"] == (4.0, 75.0)


@pytest.mark.parametrize(
    ("image_case", "content_type", "expected_detail"),
    [
        ("invalid_tiff", "image/tiff", "invalid_image"),
        ("wrong_dimensions", "image/tiff", "dimensions_mismatch:64x64"),
        ("wrong_content_type", "application/json", "unexpected_content_type"),
        ("empty_tiff", "image/tiff", "empty_response"),
        ("plain_tiff", "image/tiff", "missing_georeferencing_tags"),
    ],
    ids=["invalid-tiff", "wrong-dimensions", "wrong-content-type", "empty-tiff", "plain-tiff"],
)
def test_invalid_process_responses_are_not_saved(
    tmp_path, image_case: str, content_type: str, expected_detail: str
) -> None:
    content = {
        "invalid_tiff": b"not a tiff",
        "wrong_dimensions": _valid_tiff(64, 64),
        "wrong_content_type": b'{"error":"response detail"}',
        "empty_tiff": b"",
        "plain_tiff": _plain_tiff(),
    }[image_case]
    session = _session_responses(
        _response(200, content=content, content_type=content_type),
    )
    output: list[str] = []

    status = _run(session, tmp_path, output)

    if image_case in {"wrong_content_type", "empty_tiff"}:
        assert status == 6
        assert f"Process API error code: {expected_detail}" in output
    else:
        assert status == 8
        assert f"GeoTIFF dimensions: {expected_detail}" in output
    assert "Valid GeoTIFF received: no" in output
    assert list(tmp_path.glob("sentinel-2-process-test-*.tiff")) == []


def test_invalid_global_bbox_is_rejected_before_oauth(tmp_path) -> None:
    session = Mock()
    output: list[str] = []

    status = run_diagnostic(
        bbox=(-180, -10, 180, 10),
        session=session,
        environment={
            "COPERNICUS_CLIENT_ID": "local-test-client",
            "COPERNICUS_CLIENT_SECRET": "local-test-secret",
        },
        output_dir=tmp_path,
        output=output.append,
    )

    assert status == 2
    assert "Input error: bbox width and height must each be at most 0.25 degrees." in output
    session.request.assert_not_called()
