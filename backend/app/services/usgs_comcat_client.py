from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import requests

USGS_FDSN_EVENT_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_FEATURES_PER_RESPONSE = 500
_CHUNK_SIZE = 64 * 1024


class UsgsComcatError(Exception):
    """Safe, user-presentable category for a failed USGS query."""


class UsgsComcatTimeoutError(UsgsComcatError):
    pass


class UsgsComcatRateLimitError(UsgsComcatError):
    def __init__(self, retry_after_seconds: int | None = None) -> None:
        super().__init__("The USGS service rate limit was reached.")
        self.retry_after_seconds = retry_after_seconds


class UsgsComcatUnavailableError(UsgsComcatError):
    pass


class UsgsComcatConfigurationError(UsgsComcatUnavailableError):
    pass


class UsgsComcatResponseError(UsgsComcatError):
    pass


def _timeout_from_environment(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        value = float(raw_value)
    except ValueError as error:
        raise UsgsComcatConfigurationError(
            "The USGS client timeout configuration is invalid."
        ) from error
    if not math.isfinite(value) or not 0.1 <= value <= 30:
        raise UsgsComcatConfigurationError(
            "The USGS client timeout configuration is invalid."
        )
    return value


def _parse_retry_after(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return max(0, min(3600, int(value.strip())))
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            return None
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)
        seconds = (retry_at.astimezone(timezone.utc) - datetime.now(timezone.utc)).total_seconds()
        return max(0, min(3600, math.ceil(seconds)))


class UsgsComcatClient:
    def __init__(
        self,
        *,
        session: requests.Session | None = None,
        connect_timeout_seconds: float | None = None,
        read_timeout_seconds: float | None = None,
    ) -> None:
        self._session = session or requests.Session()
        self._owns_session = session is None
        self._connect_timeout_seconds = (
            connect_timeout_seconds
            if connect_timeout_seconds is not None
            else _timeout_from_environment("USGS_CONNECT_TIMEOUT_SECONDS", 3.0)
        )
        self._read_timeout_seconds = (
            read_timeout_seconds
            if read_timeout_seconds is not None
            else _timeout_from_environment("USGS_READ_TIMEOUT_SECONDS", 10.0)
        )
        for value in (self._connect_timeout_seconds, self._read_timeout_seconds):
            if not math.isfinite(value) or not 0.1 <= value <= 30:
                raise ValueError("USGS timeouts must be between 0.1 and 30 seconds.")

    def close(self) -> None:
        if self._owns_session:
            self._session.close()

    def query(
        self,
        *,
        start_time: datetime,
        end_time: datetime,
        west: float,
        south: float,
        east: float,
        north: float,
        min_magnitude: float | None,
        max_magnitude: float | None,
        review_status: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        params: dict[str, str | int | float] = {
            "format": "geojson",
            "starttime": _format_utc(start_time),
            "endtime": _format_utc(end_time),
            "minlatitude": south,
            "maxlatitude": north,
            "minlongitude": west,
            "maxlongitude": east,
            "orderby": "time",
            "limit": limit,
        }
        if min_magnitude is not None:
            params["minmagnitude"] = min_magnitude
        if max_magnitude is not None:
            params["maxmagnitude"] = max_magnitude
        if review_status is not None:
            params["reviewstatus"] = review_status

        try:
            response = self._session.get(
                USGS_FDSN_EVENT_URL,
                params=params,
                headers={"Accept": "application/geo+json, application/json"},
                timeout=(self._connect_timeout_seconds, self._read_timeout_seconds),
                stream=True,
                allow_redirects=False,
            )
        except requests.Timeout as error:
            raise UsgsComcatTimeoutError("The USGS request timed out.") from error
        except requests.RequestException as error:
            raise UsgsComcatUnavailableError("The USGS service could not be reached.") from error

        try:
            if response.status_code == 429:
                raise UsgsComcatRateLimitError(
                    _parse_retry_after(response.headers.get("Retry-After"))
                )
            if response.status_code >= 500:
                raise UsgsComcatUnavailableError("The USGS service returned a server error.")
            if response.status_code != 200:
                raise UsgsComcatResponseError("The USGS service rejected the query.")

            content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            if content_type not in {"application/geo+json", "application/json"}:
                raise UsgsComcatResponseError("The USGS response was not GeoJSON.")
            body = _read_bounded_response(response)
            try:
                payload = json.loads(body)
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise UsgsComcatResponseError("The USGS response contained malformed JSON.") from error
            return _validate_feature_collection(payload)
        finally:
            response.close()


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _read_bounded_response(response: requests.Response) -> bytes:
    content_length = response.headers.get("Content-Length")
    if content_length is not None:
        try:
            if int(content_length) > MAX_RESPONSE_BYTES:
                raise UsgsComcatResponseError("The USGS response exceeded the size limit.")
        except ValueError as error:
            raise UsgsComcatResponseError("The USGS response had an invalid size header.") from error

    body = bytearray()
    try:
        for chunk in response.iter_content(chunk_size=_CHUNK_SIZE):
            if not chunk:
                continue
            if len(body) + len(chunk) > MAX_RESPONSE_BYTES:
                raise UsgsComcatResponseError("The USGS response exceeded the size limit.")
            body.extend(chunk)
    except requests.Timeout as error:
        raise UsgsComcatTimeoutError("The USGS response timed out while being read.") from error
    except requests.RequestException as error:
        raise UsgsComcatUnavailableError("The USGS response could not be read.") from error
    return bytes(body)


def _validate_feature_collection(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
        raise UsgsComcatResponseError("The USGS response was not a GeoJSON FeatureCollection.")
    features = payload.get("features")
    if not isinstance(features, list):
        raise UsgsComcatResponseError("The USGS GeoJSON feature list was invalid.")
    if len(features) > MAX_FEATURES_PER_RESPONSE:
        raise UsgsComcatResponseError("The USGS response exceeded the feature limit.")
    if any(not isinstance(feature, dict) for feature in features):
        raise UsgsComcatResponseError("The USGS GeoJSON contained an invalid feature.")
    return features
