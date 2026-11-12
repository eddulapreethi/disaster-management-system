import json
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
import requests
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.earthquake_events import router
from app.schemas.canonical_environmental import CanonicalEnvironmentalRecord
from app.services.earthquake_event_service import query_earthquake_events
from app.services.usgs_comcat_client import (
    MAX_RESPONSE_BYTES,
    USGS_FDSN_EVENT_URL,
    UsgsComcatClient,
    UsgsComcatRateLimitError,
    UsgsComcatResponseError,
    UsgsComcatTimeoutError,
    UsgsComcatUnavailableError,
)
from app.utils.authentication import get_current_user


class FakeResponse:
    def __init__(self, body: bytes, *, status_code: int = 200, headers: dict | None = None):
        self.body = body
        self.status_code = status_code
        self.headers = headers or {"Content-Type": "application/geo+json"}
        self.was_closed = False

    def iter_content(self, chunk_size: int):
        for offset in range(0, len(self.body), chunk_size):
            yield self.body[offset : offset + chunk_size]

    def close(self):
        self.was_closed = True


class FakeSession:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []
        self.closed = False

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.error:
            raise self.error
        return self.response

    def close(self):
        self.closed = True


class FakeComcat:
    def __init__(self, features_by_west=None):
        self.features_by_west = features_by_west or {}
        self.calls = []
        self.closed = False

    def query(self, **kwargs):
        self.calls.append(kwargs)
        return self.features_by_west.get(kwargs["west"], [])

    def close(self):
        self.closed = True


def _feature(
    event_id="us-test-1",
    *,
    longitude=12.5,
    latitude=45.25,
    depth=8.4,
    time=None,
    updated=None,
    magnitude=4.2,
    magnitude_type="mb",
    status="reviewed",
):
    properties = {
        "id": event_id,
        "time": time if time is not None else int(datetime(2026, 11, 10, tzinfo=timezone.utc).timestamp() * 1000),
        "mag": magnitude,
        "magType": magnitude_type,
        "status": status,
        "net": "us",
        "code": "test-1",
        "url": f"https://earthquake.usgs.gov/earthquakes/eventpage/{event_id}",
        "title": "M 4.2 - test event",
        "place": "test region",
        "ids": f",{event_id},",
    }
    if updated is not None:
        properties["updated"] = updated
    coordinates = [longitude, latitude] if depth is None else [longitude, latitude, depth]
    return {
        "type": "Feature",
        "id": event_id,
        "properties": properties,
        "geometry": {"type": "Point", "coordinates": coordinates},
    }


def _query(
    client,
    *,
    west=-15,
    south=35,
    east=15,
    north=55,
    start_time=datetime(2026, 11, 1, tzinfo=timezone.utc),
    end_time=datetime(2026, 11, 12, tzinfo=timezone.utc),
    **kwargs,
):
    return query_earthquake_events(
        west=west,
        south=south,
        east=east,
        north=north,
        start_time=start_time,
        end_time=end_time,
        client=client,
        now=datetime(2026, 11, 12, 12, tzinfo=timezone.utc),
        **kwargs,
    )


def _geojson(features):
    return json.dumps({"type": "FeatureCollection", "features": features}).encode()


def test_client_uses_fixed_https_geojson_endpoint_and_bounded_timeout() -> None:
    response = FakeResponse(_geojson([]))
    session = FakeSession(response=response)
    client = UsgsComcatClient(session=session, connect_timeout_seconds=1, read_timeout_seconds=4)

    result = client.query(
        start_time=datetime(2026, 11, 1, tzinfo=timezone.utc),
        end_time=datetime(2026, 11, 2, tzinfo=timezone.utc),
        west=-10,
        south=1,
        east=10,
        north=20,
        min_magnitude=2,
        max_magnitude=6,
        review_status="reviewed",
        limit=50,
    )

    url, options = session.calls[0]
    assert url == USGS_FDSN_EVENT_URL
    assert url.startswith("https://earthquake.usgs.gov/")
    assert options["params"]["format"] == "geojson"
    assert options["params"]["reviewstatus"] == "reviewed"
    assert options["params"]["limit"] == 50
    assert options["timeout"] == (1, 4)
    assert options["stream"] is True
    assert options["allow_redirects"] is False
    assert result == []
    assert response.was_closed
    client.close()
    assert not session.closed


@pytest.mark.parametrize(
    "response",
    [
        FakeResponse(b"{not-json"),
        FakeResponse(b'{"type":"Feature","features":[]}'),
        FakeResponse(b'{"type":"FeatureCollection","features":{}}'),
        FakeResponse(b"{}", headers={"Content-Type": "text/html"}),
    ],
)
def test_client_rejects_malformed_or_non_geojson_responses(response) -> None:
    client = UsgsComcatClient(session=FakeSession(response=response))
    with pytest.raises(UsgsComcatResponseError):
        client.query(
            start_time=datetime(2026, 11, 1, tzinfo=timezone.utc),
            end_time=datetime(2026, 11, 2, tzinfo=timezone.utc),
            west=-10,
            south=1,
            east=10,
            north=20,
            min_magnitude=None,
            max_magnitude=None,
            review_status=None,
            limit=10,
        )


def test_client_enforces_response_byte_and_feature_count_limits(monkeypatch) -> None:
    response = FakeResponse(
        b"{}",
        headers={"Content-Type": "application/geo+json", "Content-Length": str(MAX_RESPONSE_BYTES + 1)},
    )
    client = UsgsComcatClient(session=FakeSession(response=response))
    with pytest.raises(UsgsComcatResponseError, match="size limit"):
        client.query(
            start_time=datetime(2026, 11, 1, tzinfo=timezone.utc),
            end_time=datetime(2026, 11, 2, tzinfo=timezone.utc),
            west=-10,
            south=1,
            east=10,
            north=20,
            min_magnitude=None,
            max_magnitude=None,
            review_status=None,
            limit=10,
        )

    monkeypatch.setattr("app.services.usgs_comcat_client.MAX_RESPONSE_BYTES", 3)
    streamed_response = FakeResponse(
        b'{"a":2}',
        headers={"Content-Type": "application/geo+json"},
    )
    client = UsgsComcatClient(session=FakeSession(response=streamed_response))
    with pytest.raises(UsgsComcatResponseError, match="size limit"):
        client.query(
            start_time=datetime(2026, 11, 1, tzinfo=timezone.utc),
            end_time=datetime(2026, 11, 2, tzinfo=timezone.utc),
            west=-10,
            south=1,
            east=10,
            north=20,
            min_magnitude=None,
            max_magnitude=None,
            review_status=None,
            limit=10,
        )

    monkeypatch.setattr("app.services.usgs_comcat_client.MAX_RESPONSE_BYTES", MAX_RESPONSE_BYTES)
    monkeypatch.setattr(
        "app.services.usgs_comcat_client.MAX_FEATURES_PER_RESPONSE",
        1,
    )
    feature_response = FakeResponse(_geojson([{}, {}]))
    client = UsgsComcatClient(session=FakeSession(response=feature_response))
    with pytest.raises(UsgsComcatResponseError, match="feature limit"):
        client.query(
            start_time=datetime(2026, 11, 1, tzinfo=timezone.utc),
            end_time=datetime(2026, 11, 2, tzinfo=timezone.utc),
            west=-10,
            south=1,
            east=10,
            north=20,
            min_magnitude=None,
            max_magnitude=None,
            review_status=None,
            limit=10,
        )


def test_client_distinguishes_timeout_rate_limit_and_provider_errors() -> None:
    request = {
        "start_time": datetime(2026, 11, 1, tzinfo=timezone.utc),
        "end_time": datetime(2026, 11, 2, tzinfo=timezone.utc),
        "west": -10,
        "south": 1,
        "east": 10,
        "north": 20,
        "min_magnitude": None,
        "max_magnitude": None,
        "review_status": None,
        "limit": 10,
    }
    with pytest.raises(UsgsComcatTimeoutError):
        UsgsComcatClient(session=FakeSession(error=requests.Timeout())).query(**request)

    limited = FakeResponse(b"ignored provider body", status_code=429, headers={"Retry-After": "17"})
    with pytest.raises(UsgsComcatRateLimitError) as raised:
        UsgsComcatClient(session=FakeSession(response=limited)).query(**request)
    assert raised.value.retry_after_seconds == 17
    assert "ignored provider body" not in str(raised.value)

    failed = FakeResponse(b"internal provider detail", status_code=503)
    with pytest.raises(UsgsComcatUnavailableError) as raised:
        UsgsComcatClient(session=FakeSession(response=failed)).query(**request)
    assert "internal provider detail" not in str(raised.value)

    rejected = FakeResponse(b"provider details", status_code=400)
    with pytest.raises(UsgsComcatResponseError) as raised:
        UsgsComcatClient(session=FakeSession(response=rejected)).query(**request)
    assert "provider details" not in str(raised.value)

    read_timeout = FakeResponse(b"")
    read_timeout.iter_content = lambda chunk_size: (_ for _ in ()).throw(requests.Timeout())
    with pytest.raises(UsgsComcatTimeoutError):
        UsgsComcatClient(session=FakeSession(response=read_timeout)).query(**request)

def test_canonical_event_preserves_time_update_depth_magnitude_status_and_provenance() -> None:
    event_time = datetime(2026, 11, 10, 4, 5, tzinfo=timezone.utc)
    updated_time = datetime(2026, 11, 11, 6, 7, tzinfo=timezone.utc)
    client = FakeComcat(
        {
            -15: [
                _feature(
                    time=int(event_time.timestamp() * 1000),
                    updated=int(updated_time.timestamp() * 1000),
                )
            ]
        }
    )

    response = _query(client)
    record = response.records[0]
    assert response.data_status == "AVAILABLE"
    assert response.freshness_status == "NOT_ASSESSED"
    assert record.contract_version == "1.0"
    assert record.record_type == "historical_event"
    assert record.hazard_type == "earthquake"
    assert record.source.provider == "USGS ComCat"
    assert record.source.source_record_id == "us-test-1"
    assert record.source.source_url.endswith("/us-test-1")
    assert record.timestamps.event_time_utc == event_time
    assert record.timestamps.retrieval_time_utc == response.retrieved_at
    assert record.source.source_metadata["source_updated_at_utc"] == "2026-11-11T06:07:00Z"
    assert record.geography.source_coordinates.longitude == 12.5
    assert record.geography.source_coordinates.latitude == 45.25
    assert record.payload.event_attributes["depth_km"] == 8.4
    assert record.payload.event_attributes["magnitude"] == 4.2
    assert record.payload.event_attributes["magnitude_type"] == "mb"
    assert record.payload.event_attributes["review_status"] == "reviewed"
    assert record.quality_status == "UNVERIFIED"
    assert record.source.license_usage_status == "UNKNOWN"


def test_missing_optional_properties_are_preserved_as_unknown_not_invented() -> None:
    event = _feature(depth=None, magnitude=None, magnitude_type=None, status=None)
    event["id"] = "us-minimal"
    event["properties"] = {"id": "us-minimal", "time": event["properties"]["time"]}
    event["geometry"] = {"type": "Point", "coordinates": [12.5, 45.25]}
    record = _query(FakeComcat({-15: [event]})).records[0]
    assert record.payload.event_attributes["depth_km"] is None
    assert record.payload.event_attributes["magnitude"] is None
    assert record.payload.event_attributes["magnitude_type"] is None
    assert record.payload.event_attributes["review_status"] is None
    assert record.source.source_url is None
    assert record.timestamps.event_time_utc is not None
    assert record.timestamps.retrieval_time_utc is not None


def test_duplicate_ids_keep_newest_provider_revision() -> None:
    event_time = int(datetime(2026, 11, 10, tzinfo=timezone.utc).timestamp() * 1000)
    older = _feature(
        time=event_time,
        updated=int(datetime(2026, 11, 10, tzinfo=timezone.utc).timestamp() * 1000),
        magnitude=3.1,
    )
    newer = _feature(
        time=event_time,
        updated=int(datetime(2026, 11, 11, tzinfo=timezone.utc).timestamp() * 1000),
        magnitude=3.7,
    )
    record = _query(FakeComcat({-15: [older, newer]})).records[0]
    assert record.payload.event_attributes["magnitude"] == 3.7
    assert record.source.source_metadata["source_updated_at_utc"] == "2026-11-11T00:00:00Z"


def test_automatic_and_reviewed_statuses_remain_source_metadata() -> None:
    automatic = _query(FakeComcat({-15: [_feature(status="automatic")]})).records[0]
    reviewed = _query(FakeComcat({-15: [_feature(status="reviewed")]})).records[0]
    assert automatic.payload.event_attributes["review_status"] == "automatic"
    assert reviewed.payload.event_attributes["review_status"] == "reviewed"
    assert automatic.quality_status == reviewed.quality_status == "UNVERIFIED"


@pytest.mark.parametrize(
    "feature",
    [
        _feature(longitude=181),
        _feature(longitude=14.5, latitude=12.5),
        _feature(magnitude=float("nan")),
        {**_feature(), "properties": {**_feature()["properties"], "time": None}},
        {**_feature(), "geometry": {"type": "Polygon", "coordinates": []}},
    ],
)
def test_invalid_coordinates_and_event_values_reject_provider_response(feature) -> None:
    with pytest.raises(UsgsComcatResponseError):
        _query(FakeComcat({-15: [feature]}))


def test_non_finite_integer_measurements_are_rejected_safely() -> None:
    feature = _feature()
    feature["properties"]["mag"] = 10**10000
    with pytest.raises(UsgsComcatResponseError):
        _query(FakeComcat({-15: [feature]}))


def test_antimeridian_query_splits_bounds_and_deduplicates_results() -> None:
    feature = _feature(longitude=179.5)
    client = FakeComcat({170: [feature], -180: [feature]})
    result = _query(client, west=170, east=-170, south=30, north=50)

    assert len(client.calls) == 2
    assert [(call["west"], call["east"]) for call in client.calls] == [
        (170, 180.0),
        (-180.0, -170),
    ]
    assert result.returned_events == 1
    assert result.records[0].geography.source_coordinates.longitude == 179.5


def test_empty_results_and_broad_or_invalid_filters_are_distinct() -> None:
    empty = _query(FakeComcat())
    assert empty.records == []
    assert empty.data_status == "NO_MATCHING_EVENTS"

    with pytest.raises(ValueError, match="longitude span"):
        _query(FakeComcat(), west=-180, east=180)
    with pytest.raises(ValueError, match="latitude span"):
        _query(FakeComcat(), south=-20, north=20)
    with pytest.raises(ValueError, match="30 days"):
        _query(
            FakeComcat(),
            start_time=datetime(2026, 10, 1, tzinfo=timezone.utc),
            end_time=datetime(2026, 11, 12, tzinfo=timezone.utc),
        )
    with pytest.raises(ValueError, match="min_magnitude"):
        _query(FakeComcat(), min_magnitude=6, max_magnitude=3)


def _api_client(authenticated: bool) -> TestClient:
    application = FastAPI()
    application.include_router(router, prefix="/api")
    if authenticated:
        application.dependency_overrides[get_current_user] = lambda: object()
    return TestClient(application)


def test_api_requires_authentication_and_validates_bounded_query(monkeypatch) -> None:
    params = {
        "west": -15,
        "south": 35,
        "east": 15,
        "north": 55,
    }
    unauthenticated = _api_client(False).get("/api/earthquake-events", params=params)
    assert unauthenticated.status_code == 401

    client = _api_client(True)
    with patch("app.api.earthquake_events.query_earthquake_events") as query:
        query.return_value = _query(FakeComcat())
        response = client.get("/api/earthquake-events", params=params)
    assert response.status_code == 200
    assert response.json()["data_status"] == "NO_MATCHING_EVENTS"
    assert response.json()["provider"] == "USGS ComCat"

    missing_bound = client.get(
        "/api/earthquake-events",
        params={"west": -20, "south": 35, "east": 20},
    )
    assert missing_bound.status_code == 422

    broad = client.get(
        "/api/earthquake-events",
        params={**params, "west": -90, "east": 90},
    )
    assert broad.status_code == 422

    naive_time = client.get(
        "/api/earthquake-events",
        params={**params, "start_time": "2026-11-01T00:00:00"},
    )
    assert naive_time.status_code == 422


def test_api_returns_safe_provider_error_and_retry_after() -> None:
    client = _api_client(True)
    params = {"west": -20, "south": 35, "east": 20, "north": 55}
    with patch(
        "app.api.earthquake_events.query_earthquake_events",
        side_effect=UsgsComcatRateLimitError(17),
    ):
        response = client.get("/api/earthquake-events", params=params)
    assert response.status_code == 503
    assert response.headers["Retry-After"] == "17"
    assert "provider body" not in response.text


def test_endpoint_does_not_return_noncanonical_event_records() -> None:
    record = _query(FakeComcat({-15: [_feature()]})).records[0]
    assert isinstance(record, CanonicalEnvironmentalRecord)
    assert record.contract_version == "1.0"
