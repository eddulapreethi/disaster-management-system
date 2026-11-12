from unittest.mock import Mock

import pytest
from requests.exceptions import ConnectionError, Timeout

from scripts.copernicus_auth_diagnostic import (
    CATALOG_SEARCH_URL,
    TOKEN_URL,
    run_diagnostic,
)


def _response(status_code: int, payload: object) -> Mock:
    response = Mock()
    response.status_code = status_code
    response.ok = 200 <= status_code < 400
    response.json.return_value = payload
    return response


def _credentials() -> dict[str, str]:
    return {
        "COPERNICUS_CLIENT_ID": "local-test-client",
        "COPERNICUS_CLIENT_SECRET": "local-test-secret",
    }


def test_success_reports_status_and_feature_count_without_secrets_or_token() -> None:
    session = Mock()
    session.post.side_effect = [
        _response(200, {"access_token": "private-mock-token"}),
        _response(200, {"features": [{"id": "test-item"}]}),
    ]
    output: list[str] = []

    result = run_diagnostic(session=session, environment=_credentials(), output=output.append)

    assert result == 0
    assert "Token endpoint HTTP status: 200" in output
    assert "Access token received: yes (value withheld)" in output
    assert "Catalog endpoint HTTP status: 200" in output
    assert "Catalog features returned: 1" in output
    transcript = "\n".join(output)
    assert "local-test-secret" not in transcript
    assert "private-mock-token" not in transcript
    assert session.post.call_count == 2
    token_request = session.post.call_args_list[0]
    assert token_request.args == (TOKEN_URL,)
    assert token_request.kwargs["data"] == {
        "grant_type": "client_credentials",
        "client_id": "local-test-client",
        "client_secret": "local-test-secret",
    }
    catalog_request = session.post.call_args_list[1]
    assert catalog_request.args == (CATALOG_SEARCH_URL,)
    assert catalog_request.kwargs["headers"]["Authorization"].startswith("Bearer ")
    assert catalog_request.kwargs["json"]["limit"] == 1


@pytest.mark.parametrize(
    ("status_code", "error_code"),
    [(401, "invalid_client"), (403, "unauthorized_client")],
)
def test_token_endpoint_rejection_is_reported_without_catalog_call(status_code, error_code) -> None:
    session = Mock()
    session.post.return_value = _response(
        status_code,
        {"error": error_code, "error_description": "must-not-be-shown"},
    )
    output: list[str] = []

    result = run_diagnostic(session=session, environment=_credentials(), output=output.append)

    assert result == 4
    assert f"Token endpoint HTTP status: {status_code}" in output
    assert f"Token endpoint error code: {error_code}" in output
    assert session.post.call_count == 1
    assert "must-not-be-shown" not in "\n".join(output)


@pytest.mark.parametrize(
    ("error", "sanitized_code"),
    [
        (Timeout("opaque-sensitive-payload"), "timeout"),
        (ConnectionError("opaque-sensitive-payload"), "network_error"),
    ],
)
def test_token_endpoint_network_failures_are_sanitized(error, sanitized_code) -> None:
    session = Mock()
    session.post.side_effect = error
    output: list[str] = []

    result = run_diagnostic(session=session, environment=_credentials(), output=output.append)

    assert result == 3
    assert f"Token endpoint error code: {sanitized_code}" in output
    assert "opaque-sensitive-payload" not in "\n".join(output)
    assert session.post.call_count == 1


def test_malformed_token_json_is_reported_and_catalog_is_not_requested() -> None:
    session = Mock()
    response = _response(200, {})
    response.json.side_effect = ValueError("private response body")
    session.post.return_value = response
    output: list[str] = []

    result = run_diagnostic(session=session, environment=_credentials(), output=output.append)

    assert result == 5
    assert "Token endpoint HTTP status: 200" in output
    assert "Token endpoint error code: malformed_response" in output
    assert session.post.call_count == 1
    assert "private response body" not in "\n".join(output)


def test_token_response_without_access_token_fails_closed() -> None:
    session = Mock()
    session.post.return_value = _response(200, {"expires_in": 300})
    output: list[str] = []

    result = run_diagnostic(session=session, environment=_credentials(), output=output.append)

    assert result == 5
    assert "Access token received: no" in output
    assert "Token endpoint error code: malformed_response" in output
    assert session.post.call_count == 1


def test_missing_credentials_never_make_external_requests() -> None:
    session = Mock()
    output: list[str] = []

    result = run_diagnostic(session=session, environment={}, output=output.append)

    assert result == 2
    assert "Client ID present: no" in output
    assert "Client secret present: no" in output
    session.post.assert_not_called()


@pytest.mark.parametrize(
    ("status_code", "error_code"),
    [(401, "unauthorized"), (403, "forbidden")],
)
def test_catalog_authorization_failure_is_reported_separately(status_code, error_code) -> None:
    session = Mock()
    session.post.side_effect = [
        _response(200, {"access_token": "private-mock-token"}),
        _response(status_code, {"error": error_code}),
    ]
    output: list[str] = []

    result = run_diagnostic(session=session, environment=_credentials(), output=output.append)

    assert result == 7
    assert "Token endpoint HTTP status: 200" in output
    assert f"Catalog endpoint HTTP status: {status_code}" in output
    assert f"Catalog endpoint error code: {error_code}" in output
    assert "private-mock-token" not in "\n".join(output)


def test_catalog_network_error_is_reported_after_successful_authentication() -> None:
    session = Mock()
    session.post.side_effect = [
        _response(200, {"access_token": "private-mock-token"}),
        Timeout("private-mock-token"),
    ]
    output: list[str] = []

    result = run_diagnostic(session=session, environment=_credentials(), output=output.append)

    assert result == 6
    assert "Catalog endpoint HTTP status: unavailable" in output
    assert "Catalog endpoint error code: timeout" in output
    assert "private-mock-token" not in "\n".join(output)


@pytest.mark.parametrize(
    "catalog_response",
    [
        _response(200, {}),
        _response(200, {"features": None}),
    ],
)
def test_malformed_catalog_payload_is_reported_without_payload_details(catalog_response) -> None:
    session = Mock()
    session.post.side_effect = [
        _response(200, {"access_token": "private-mock-token"}),
        catalog_response,
    ]
    output: list[str] = []

    result = run_diagnostic(session=session, environment=_credentials(), output=output.append)

    assert result == 8
    assert "Catalog endpoint HTTP status: 200" in output
    assert "Catalog endpoint error code: malformed_response" in output
    assert "Catalog features returned: unavailable" in output
    assert "private-mock-token" not in "\n".join(output)


def test_malformed_catalog_json_is_reported_without_response_body() -> None:
    session = Mock()
    malformed = _response(200, {})
    malformed.json.side_effect = ValueError("private response body")
    session.post.side_effect = [
        _response(200, {"access_token": "private-mock-token"}),
        malformed,
    ]
    output: list[str] = []

    result = run_diagnostic(session=session, environment=_credentials(), output=output.append)

    assert result == 8
    assert "private response body" not in "\n".join(output)
