"""Run a sanitized, read-only Copernicus OAuth and Catalog connectivity check."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

import requests
from requests.exceptions import RequestException, Timeout

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Importing the backend package runs its configured backend/.env loader.
import app  # noqa: E402, F401
from app.services.copernicus_service import CATALOG_SEARCH_URL, TOKEN_URL  # noqa: E402

TIMEOUT_SECONDS = 20
CATALOG_COLLECTION = "sentinel-2-l2a"
CATALOG_BBOX = [76.26, 9.92, 76.28, 9.94]
SAFE_ERROR_CODES = {
    "invalid_client",
    "unauthorized_client",
    "invalid_request",
    "invalid_scope",
    "invalid_grant",
    "invalid_token",
    "server_error",
    "temporarily_unavailable",
    "unauthorized",
    "forbidden",
}


def _error_code(response: Any) -> str:
    try:
        payload = response.json()
    except (AttributeError, ValueError):
        return "unavailable"
    code = payload.get("error") if isinstance(payload, dict) else None
    return code if isinstance(code, str) and code in SAFE_ERROR_CODES else "unavailable"


def _network_error_code(error: RequestException) -> str:
    return "timeout" if isinstance(error, Timeout) else "network_error"


def _print(lines: list[str], output: Callable[[str], None]) -> None:
    for line in lines:
        output(line)


def run_diagnostic(
    *,
    session: Any | None = None,
    environment: Mapping[str, str] | None = None,
    output: Callable[[str], None] = print,
) -> int:
    """Run one token request and at most one read-only Catalog request."""
    env = os.environ if environment is None else environment
    client_id = (env.get("COPERNICUS_CLIENT_ID") or "").strip()
    client_secret = (env.get("COPERNICUS_CLIENT_SECRET") or "").strip()
    output(f"Client ID present: {'yes' if client_id else 'no'}")
    output(f"Client secret present: {'yes' if client_secret else 'no'}")
    if not client_id or not client_secret:
        output("Result: credentials are unavailable; no external request was made.")
        return 2

    http = session or requests.Session()
    token_payload = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }
    try:
        token_response = http.post(
            TOKEN_URL,
            data=token_payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=TIMEOUT_SECONDS,
        )
    except RequestException as error:
        _print(
            [
                "Token endpoint HTTP status: unavailable",
                f"Token endpoint error code: {_network_error_code(error)}",
                "Result: token request failed before an HTTP response was received.",
            ],
            output,
        )
        return 3

    output(f"Token endpoint HTTP status: {token_response.status_code}")
    if not token_response.ok:
        code = _error_code(token_response)
        output(f"Token endpoint error code: {code}")
        output("Result: OAuth token acquisition failed; no Catalog request was made.")
        if token_response.status_code in {401, 403}:
            output("Next step: verify that the OAuth client is active and its ID/secret pair is current.")
        return 4

    try:
        token_data = token_response.json()
    except ValueError:
        output("Access token received: no")
        output("Token endpoint error code: malformed_response")
        output("Result: token endpoint returned successful HTTP status with invalid JSON.")
        return 5

    access_token = token_data.get("access_token") if isinstance(token_data, dict) else None
    if not isinstance(access_token, str) or not access_token.strip():
        output("Access token received: no")
        output("Token endpoint error code: malformed_response")
        output("Result: token endpoint response did not contain a valid access token.")
        return 5

    output("Access token received: yes (value withheld)")
    now = datetime.now(timezone.utc)
    catalog_body = {
        "bbox": CATALOG_BBOX,
        "datetime": (
            f"{(now - timedelta(days=14)).isoformat().replace('+00:00', 'Z')}/"
            f"{now.isoformat().replace('+00:00', 'Z')}"
        ),
        "collections": [CATALOG_COLLECTION],
        "limit": 1,
    }
    try:
        catalog_response = http.post(
            CATALOG_SEARCH_URL,
            json=catalog_body,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/geo+json",
            },
            timeout=TIMEOUT_SECONDS,
        )
    except RequestException as error:
        output("Catalog endpoint HTTP status: unavailable")
        output(f"Catalog endpoint error code: {_network_error_code(error)}")
        output("Result: token acquisition succeeded; Catalog request failed before an HTTP response.")
        return 6

    output(f"Catalog endpoint HTTP status: {catalog_response.status_code}")
    if not catalog_response.ok:
        output(f"Catalog endpoint error code: {_error_code(catalog_response)}")
        output("Result: token acquisition succeeded; Catalog authorization/request failed.")
        return 7

    try:
        catalog_payload = catalog_response.json()
    except ValueError:
        output("Catalog endpoint error code: malformed_response")
        output("Catalog features returned: unavailable")
        output("Result: token acquisition succeeded; Catalog returned invalid JSON.")
        return 8
    features = catalog_payload.get("features") if isinstance(catalog_payload, dict) else None
    if not isinstance(features, list):
        output("Catalog endpoint error code: malformed_response")
        output("Catalog features returned: unavailable")
        output("Result: token acquisition succeeded; Catalog response has no valid features list.")
        return 8

    output(f"Catalog endpoint error code: none")
    output(f"Catalog features returned: {len(features)}")
    output("Result: token and Catalog requests succeeded; this verifies catalog access only.")
    return 0


def main() -> int:
    return run_diagnostic()


if __name__ == "__main__":
    raise SystemExit(main())
