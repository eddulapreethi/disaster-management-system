from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import Session

from app.api.environmental_data import router
from app.database.connection import Base
from app.database.database import get_db
from app.models.disaster import Disaster
from app.models.hydrological_observation import HydrologicalObservation
from app.models.weather_observation import WeatherObservation
from app.services.environmental_data_service import _mark_duplicates, _weather_record, query_environmental_data
from app.utils.authentication import get_current_user


@pytest.fixture
def database():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


def _client(db: Session, *, authenticated: bool = True) -> TestClient:
    application = FastAPI()
    application.include_router(router, prefix="/api")
    application.dependency_overrides[get_db] = lambda: db
    if authenticated:
        application.dependency_overrides[get_current_user] = lambda: object()
    return TestClient(application)


def _weather(
    *,
    station_id: str = "internal-station",
    latitude: float = 51.5072,
    longitude: float = -0.1276,
    observation_time: datetime | None = None,
    temperature_c: float | None = 12.5,
    provider_metadata: dict | None = None,
) -> WeatherObservation:
    observed = observation_time or datetime.now(timezone.utc) - timedelta(minutes=10)
    return WeatherObservation(
        station_id=station_id,
        station_name="London point",
        source="open-meteo",
        latitude=latitude,
        longitude=longitude,
        temperature_c=temperature_c,
        humidity_percent=None,
        precipitation_mm=0.0,
        rain_mm=None,
        wind_speed_kmh=8.0,
        pressure_hpa=None,
        observation_time=observed,
        fetched_at=datetime.now(timezone.utc),
        provider_metadata=provider_metadata or {"timezone": "UTC", "raw": {"temperature_2m": temperature_c}},
    )


def test_query_preserves_provenance_null_measurements_and_event_time_semantics(database) -> None:
    observed = datetime.now(timezone.utc) - timedelta(minutes=10)
    weather = _weather(temperature_c=None, observation_time=observed)
    hydrology = HydrologicalObservation(
        source="nwdp:cwc_krishna_water_level",
        source_resource_id="resource-krishna",
        source_record_id=123,
        station_id="generated-internal-key",
        station_name="River gauge",
        river_name="Krishna",
        state_name="Andhra Pradesh",
        district_name=None,
        latitude=16.5,
        longitude=80.6,
        water_level=2.4,
        discharge=None,
        rainfall=None,
        observation_time=observed,
        fetched_at=datetime.now(timezone.utc),
        provider_metadata={"source_timestamp_raw": "12-11-2026 10:00"},
    )
    report = Disaster(
        name="Reported flood",
        disaster_type="flood",
        description="Unverified user report",
        latitude=9.95,
        longitude=76.25,
        status="reported",
        created_at=observed,
    )
    database.add_all([weather, hydrology, report])
    database.commit()

    result = query_environmental_data(database)
    records = {record.category: record for record in result.records}

    assert set(records) == {"weather_observation", "hydrological_observation"}
    weather_record = records["weather_observation"]
    assert weather_record.values["temperature_c"] is None
    assert weather_record.quality_status == "PARTIAL"
    assert weather_record.provider == "Open-Meteo"
    assert weather_record.source_record_id is None
    assert weather_record.observation_time.replace(tzinfo=timezone.utc) == observed
    assert weather_record.raw_source_values["raw"]["temperature_2m"] is None
    assert weather_record.freshness_status == "READY"
    assert weather_record.canonical_record.contract_version == "1.0"
    assert weather_record.canonical_record.record_type == "observation"
    assert weather_record.canonical_record.payload.measurement_basis == "model_derived"
    assert weather_record.canonical_record.timestamps.observation_time_utc == observed
    assert weather_record.canonical_record.local_record_id == weather.id

    hydro_record = records["hydrological_observation"]
    assert hydro_record.source_record_id == 123
    assert hydro_record.geographic_metadata["station_id_is_internal"] is True
    assert hydro_record.units["water_level"] == "m"
    assert hydro_record.quality_status == "UNVERIFIED"
    assert "datum" in " ".join(hydro_record.validation_findings)
    assert hydro_record.canonical_record.source.source_record_id == 123
    assert hydro_record.canonical_record.availability_status == "REGIONAL"
    assert hydro_record.canonical_record.timestamps.timezone_assumption is None

    source_status = {source.category: source.status for source in result.sources}
    event_source = next(source for source in result.sources if source.category == "disaster_event_report")
    assert source_status["disaster_event_report"] == "UNVERIFIED"
    assert event_source.matching_records == 0
    assert "withheld" in event_source.details
    assert source_status["weather_forecast"] == "NOT_PERSISTED"
    assert source_status["satellite_scene_metadata"] == "NOT_PERSISTED"
    assert source_status["geographic_reference_dataset"] == "REGIONAL"


def test_filters_by_bbox_location_provider_category_and_observation_time(database) -> None:
    recent = datetime.now(timezone.utc) - timedelta(hours=1)
    old = datetime.now(timezone.utc) - timedelta(days=1)
    database.add_all(
        [
            _weather(station_id="london", observation_time=recent),
            _weather(station_id="new-york", latitude=40.7128, longitude=-74.0060, observation_time=recent),
            _weather(station_id="old-london", observation_time=old),
        ]
    )
    database.commit()

    result = query_environmental_data(
        database,
        provider="Open-Meteo Forecast API",
        category="weather_observation",
        bbox=(-1, 50, 1, 53),
        location=(51.5072, -0.1276, 10),
        start_time=recent - timedelta(minutes=1),
        end_time=recent + timedelta(minutes=1),
    )

    assert len(result.records) == 1
    assert result.records[0].geographic_metadata["station_id"] == "london"
    assert result.filters["time_filter_semantics"].startswith("Observation time")


def test_queries_are_independent_across_continents_and_empty_locations(database) -> None:
    observed = datetime.now(timezone.utc) - timedelta(minutes=10)
    database.add_all(
        [
            _weather(station_id="new-york", latitude=40.7128, longitude=-74.0060, observation_time=observed),
            _weather(station_id="sydney", latitude=-33.8688, longitude=151.2093, observation_time=observed),
            _weather(station_id="nairobi", latitude=-1.2921, longitude=36.8219, observation_time=observed),
        ]
    )
    database.commit()

    queries = [
        (40.7128, -74.0060, "new-york"),
        (-33.8688, 151.2093, "sydney"),
        (-1.2921, 36.8219, "nairobi"),
    ]
    for latitude, longitude, expected_station in queries:
        result = query_environmental_data(
            database,
            category="weather_observation",
            location=(latitude, longitude, 10),
        )
        assert [row.geographic_metadata["station_id"] for row in result.records] == [expected_station]

    empty_result = query_environmental_data(
        database,
        category="weather_observation",
        location=(0, 0, 10),
    )
    assert empty_result.records == []
    assert empty_result.sources[0].status == "NO_MATCHING_STORED_RECORDS"


def test_spatial_filters_are_applied_before_result_limit(database) -> None:
    database.add_all(
        [
            _weather(station_id="latest-new-york", latitude=40.7128, longitude=-74.0060),
            _weather(
                station_id="older-london",
                latitude=51.5072,
                longitude=-0.1276,
                observation_time=datetime.now(timezone.utc) - timedelta(minutes=20),
            ),
        ]
    )
    database.commit()

    result = query_environmental_data(
        database,
        category="weather_observation",
        bbox=(-1, 50, 1, 53),
        limit=1,
    )

    assert len(result.records) == 1
    assert result.records[0].geographic_metadata["station_id"] == "older-london"


def test_antimeridian_bounds_match_both_longitude_sides(database) -> None:
    database.add_all(
        [
            _weather(station_id="east-dateline", latitude=10, longitude=179.5),
            _weather(station_id="west-dateline", latitude=10, longitude=-179.5),
            _weather(station_id="greenwich", latitude=10, longitude=0),
        ]
    )
    database.commit()

    response = _client(database).get(
        "/api/environmental-data",
        params={"west": 170, "south": 5, "east": -170, "north": 15},
    )

    assert response.status_code == 200
    assert {
        row["geographic_metadata"]["station_id"] for row in response.json()["records"]
    } == {"east-dateline", "west-dateline"}


def test_radius_filter_checks_exact_distance_before_pagination(database) -> None:
    observed = datetime.now(timezone.utc) - timedelta(minutes=10)
    database.add_all(
        [
            _weather(
                station_id="outside-radius-corner",
                latitude=51.5072 + 0.18,
                longitude=-0.1276 + 0.3,
                observation_time=observed + timedelta(minutes=1),
            ),
            _weather(
                station_id="inside-radius",
                latitude=51.5072,
                longitude=-0.1276,
                observation_time=observed,
            ),
        ]
    )
    database.commit()

    result = query_environmental_data(
        database,
        category="weather_observation",
        location=(51.5072, -0.1276, 25),
        limit=1,
    )

    assert len(result.records) == 1
    assert result.records[0].geographic_metadata["station_id"] == "inside-radius"


def test_pagination_is_stable_and_reports_more_pages(database) -> None:
    base = datetime.now(timezone.utc) - timedelta(hours=1)
    database.add_all(
        [
            _weather(station_id=f"station-{index}", observation_time=base)
            for index in range(5)
        ]
    )
    database.commit()

    first_page = query_environmental_data(database, category="weather_observation", limit=2)
    second_page = query_environmental_data(database, category="weather_observation", limit=2, offset=2)
    last_page = query_environmental_data(database, category="weather_observation", limit=2, offset=4)

    first_ids = [record.record_id for record in first_page.records]
    second_ids = [record.record_id for record in second_page.records]
    last_ids = [record.record_id for record in last_page.records]
    assert first_page.has_more is True
    assert second_page.has_more is True
    assert last_page.has_more is False
    assert first_page.pagination.model_dump() == {
        "limit": 2,
        "offset": 0,
        "returned_records": 2,
        "count_scope": "RETURNED_PAGE",
    }
    weather_source = next(source for source in first_page.sources if source.category == "weather_observation")
    assert weather_source.matching_records == 2
    assert weather_source.count_scope == "RETURNED_PAGE"
    assert second_page.pagination.returned_records == 2
    assert last_page.pagination.returned_records == 1
    assert len(set(first_ids + second_ids + last_ids)) == 5
    assert first_ids + second_ids + last_ids == sorted(first_ids + second_ids + last_ids, reverse=True)


def test_timezone_offsets_are_normalized_for_date_boundary_filters(database) -> None:
    boundary = datetime(2026, 1, 1, tzinfo=timezone.utc)
    database.add(_weather(station_id="utc-boundary", observation_time=boundary))
    database.commit()

    result = query_environmental_data(
        database,
        category="weather_observation",
        start_time=datetime.fromisoformat("2026-01-01T01:00:00+01:00"),
        end_time=datetime.fromisoformat("2026-01-01T01:00:00+01:00"),
    )

    assert [record.geographic_metadata["station_id"] for record in result.records] == ["utc-boundary"]


def test_authenticated_catalog_withholds_application_report_details(database) -> None:
    database.add(_weather())
    database.add(
        Disaster(
            name="Private report title",
            disaster_type="flood",
            description="Sensitive report description",
            latitude=9.95,
            longitude=76.25,
            status="reported",
        )
    )
    database.commit()

    response = _client(database).get("/api/environmental-data")

    assert response.status_code == 200
    payload = response.json()
    serialized_payload = response.text
    assert "Private report title" not in serialized_payload
    assert "Sensitive report description" not in serialized_payload
    event_source = next(
        source for source in response.json()["sources"]
        if source["category"] == "disaster_event_report"
    )
    assert event_source["status"] == "UNVERIFIED"
    assert event_source["matching_records"] == 0
    assert event_source["count_scope"] == "RETURNED_PAGE"


def test_catalog_adds_canonical_weather_without_removing_legacy_fields(database) -> None:
    database.add(_weather())
    database.commit()

    response = _client(database).get(
        "/api/environmental-data",
        params={"category": "weather_observation"},
    )

    assert response.status_code == 200
    legacy_weather = response.json()["records"][0]
    assert legacy_weather["values"]["temperature_c"] == 12.5
    assert legacy_weather["units"]["temperature_c"] == "°C"
    assert legacy_weather["canonical_record"]["contract_version"] == "1.0"
    assert legacy_weather["canonical_record"]["payload"]["measurement_basis"] == "model_derived"


def test_freshness_stale_invalid_and_unavailable_records_are_not_fabricated(database, monkeypatch) -> None:
    monkeypatch.setenv("WEATHER_MAX_AGE_SECONDS", "600")
    stale = _weather(station_id="stale", observation_time=datetime.now(timezone.utc) - timedelta(hours=2))
    database.add(stale)
    database.commit()

    response = _client(database).get("/api/environmental-data")
    assert response.status_code == 200
    records = {item["geographic_metadata"]["station_id"]: item for item in response.json()["records"]}
    assert records["stale"]["freshness_status"] == "STALE"
    assert {
        source["category"]: source["status"] for source in response.json()["sources"]
    }["weather_observation"] == "STALE"

    invalid = _weather(station_id="invalid", latitude=91)
    invalid_assessment = _weather_record(invalid, datetime.now(timezone.utc))
    assert invalid_assessment["quality_status"] == "INVALID"
    invalid_measurement = _weather(station_id="invalid-measurement", temperature_c=float("nan"))
    invalid_measurement.provider_metadata = {"timezone": "UTC", "raw": {"temperature_2m": float("nan")}}
    measurement_assessment = _weather_record(invalid_measurement, datetime.now(timezone.utc))
    assert measurement_assessment["quality_status"] == "INVALID"
    assert "temperature_c is non-finite" in " ".join(measurement_assessment["validation_findings"])
    assert measurement_assessment["values"]["temperature_c"] == "NaN"
    assert measurement_assessment["raw_source_values"]["raw"]["temperature_2m"] == "NaN"

    empty_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(empty_engine)
    with Session(empty_engine) as empty_db:
        empty_response = _client(empty_db).get("/api/environmental-data")
    empty_engine.dispose()
    assert empty_response.status_code == 200
    empty_payload = empty_response.json()
    assert empty_payload["records"] == []
    empty_hydrology = next(
        source for source in empty_payload["sources"]
        if source["category"] == "hydrological_observation"
    )
    assert empty_hydrology["status"] == "NO_MATCHING_STORED_RECORDS"
    assert empty_hydrology["count_scope"] == "RETURNED_PAGE"
    assert "provider coverage was not checked" in empty_payload["sources"][0]["details"]
    assert empty_payload["pagination"] == {
        "limit": 100,
        "offset": 0,
        "returned_records": 0,
        "count_scope": "RETURNED_PAGE",
    }


def test_mixed_freshness_records_are_reported_as_partial_not_available(database, monkeypatch) -> None:
    monkeypatch.setenv("WEATHER_MAX_AGE_SECONDS", "600")
    now = datetime.now(timezone.utc)
    database.add_all(
        [
            _weather(station_id="fresh", observation_time=now - timedelta(minutes=5)),
            _weather(station_id="stale", observation_time=now - timedelta(hours=2)),
        ]
    )
    database.commit()

    response = _client(database).get("/api/environmental-data")

    assert response.status_code == 200
    weather_source = next(
        source for source in response.json()["sources"]
        if source["category"] == "weather_observation"
    )
    assert weather_source["status"] == "PARTIAL"
    assert weather_source["matching_records"] == 2


def test_conflicting_duplicates_are_flagged_and_original_values_retained() -> None:
    first = {
        "category": "weather_observation",
        "provider": "Open-Meteo",
        "geographic_metadata": {"station_id": "same"},
        "observation_time": datetime(2026, 11, 12, tzinfo=timezone.utc),
        "raw_source_values": {"provider_source": "open-meteo"},
        "values": {"temperature_c": 10.0},
        "validation_findings": [],
        "duplicate_key": False,
        "conflicting_values": False,
    }
    second = {**first, "values": {"temperature_c": 11.0}, "validation_findings": []}

    _mark_duplicates([first, second])

    assert first["duplicate_key"] and second["duplicate_key"]
    assert first["conflicting_values"] and second["conflicting_values"]
    assert first["values"]["temperature_c"] == 10.0
    assert second["values"]["temperature_c"] == 11.0


@pytest.mark.parametrize(
    ("params", "message"),
    [
        ({"west": -1, "south": 1, "east": 1, "north": -1}, "Bounding box"),
        ({"latitude": 0}, "both latitude and longitude"),
        ({"category": "flood_score"}, "category must be one of"),
        ({"start_time": "2026-11-12T00:00:00"}, "timezone"),
        ({"radius_km": 0}, "greater than 0"),
        ({"offset": 10001}, "less than or equal to 10000"),
    ],
)
def test_invalid_filters_fail_explicitly(database, params, message) -> None:
    with _client(database) as client:
        response = client.get("/api/environmental-data", params=params)
    assert response.status_code == 422
    assert message.lower() in response.text.lower()


def test_non_finite_location_filter_is_rejected(database) -> None:
    with pytest.raises(ValueError, match="valid WGS 84"):
        query_environmental_data(database, location=(float("nan"), 0, 10))


def test_catalog_is_authenticated(database) -> None:
    with _client(database, authenticated=False) as client:
        response = client.get("/api/environmental-data")
    assert response.status_code == 401
