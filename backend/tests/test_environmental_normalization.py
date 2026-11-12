from datetime import datetime, timezone

import pytest
from pydantic import TypeAdapter, ValidationError

from app.schemas.canonical_environmental import (
    HAZARD_TAXONOMY,
    CanonicalEnvironmentalRecord,
    CanonicalGeography,
    CanonicalSource,
    CanonicalTimestamps,
    ForecastPayload,
    HazardIdentifier,
    ObservationPayload,
    WGS84BoundingBox,
    WGS84Point,
)
from app.services.environmental_normalization_service import (
    normalize_hydrology_record,
    normalize_measurement,
    normalize_satellite_acquisition,
    normalize_source_timestamp,
    normalize_weather_record,
)


@pytest.mark.parametrize(
    ("source_value", "source_unit", "target_unit", "expected"),
    [
        (68, "°F", "°C", 20),
        (10, "m/s", "km/h", 36),
        (1500, "mm", "m", 1.5),
        (None, "mm", "mm", None),
    ],
)
def test_known_unit_conversions_preserve_missing_values(
    source_value, source_unit, target_unit, expected
) -> None:
    normalized, _ = normalize_measurement(source_value, source_unit, target_unit)
    assert normalized == pytest.approx(expected) if expected is not None else normalized is None


@pytest.mark.parametrize(
    ("source_unit", "target_unit"),
    [("unknown", "mm"), ("m", "km/h"), (None, "°C")],
)
def test_unknown_or_incompatible_units_are_rejected(source_unit, target_unit) -> None:
    with pytest.raises(ValueError, match="unit|dimension"):
        normalize_measurement(1, source_unit, target_unit)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_non_finite_measurement_values_are_rejected(value) -> None:
    with pytest.raises(ValueError, match="finite"):
        normalize_measurement(value, "mm", "mm")


def test_offset_timestamp_preserves_source_text_and_normalizes_to_utc() -> None:
    raw = "2026-01-01T01:00:00+01:00"
    normalized = normalize_source_timestamp(raw)

    assert normalized.source_timestamp_raw == raw
    assert normalized.source_timezone == "UTC+01:00"
    assert normalized.timezone_assumption is None
    assert normalized.utc == datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_naive_timestamp_requires_an_explicit_timezone_assumption() -> None:
    with pytest.raises(ValueError, match="no timezone"):
        normalize_source_timestamp("2026-01-01T10:00:00")

    normalized = normalize_source_timestamp(
        "2026-01-01T10:00:00",
        timezone_assumption="Asia/Kolkata",
    )
    assert normalized.utc == datetime(2026, 1, 1, 4, 30, tzinfo=timezone.utc)
    assert normalized.source_timezone == "Asia/Kolkata"
    assert normalized.timezone_assumption == "Asia/Kolkata"


@pytest.mark.parametrize(
    "value",
    ["2026-03-29T02:30:00", "2026-10-25T02:30:00"],
)
def test_nonexistent_and_ambiguous_wall_times_are_rejected(value) -> None:
    with pytest.raises(ValueError, match="nonexistent|Ambiguous"):
        normalize_source_timestamp(value, source_timezone="Europe/Paris")


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [(-90, -180), (90, 180), (0, 0), (45.5, -179.999)],
)
def test_wgs84_coordinates_accept_global_boundaries(latitude, longitude) -> None:
    assert WGS84Point(latitude=latitude, longitude=longitude).model_dump() == {
        "latitude": latitude,
        "longitude": longitude,
    }


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [(90.001, 0), (-90.001, 0), (0, 180.001), (float("nan"), 0), (0, float("inf"))],
)
def test_wgs84_coordinates_reject_out_of_range_and_non_finite_values(latitude, longitude) -> None:
    with pytest.raises(ValidationError):
        WGS84Point(latitude=latitude, longitude=longitude)


def test_antimeridian_bounding_box_is_valid_and_explicit() -> None:
    bounds = WGS84BoundingBox(west=170, south=-20, east=-170, north=20)
    assert bounds.crosses_antimeridian is True
    assert bounds.model_dump() == {"west": 170, "south": -20, "east": -170, "north": 20}

    zero_width = WGS84BoundingBox(west=10, south=-20, east=10, north=20)
    assert zero_width.crosses_antimeridian is False

    with pytest.raises(ValidationError):
        WGS84BoundingBox(west=170, south=20, east=-170, north=-20)


def test_hazard_taxonomy_is_explicit_and_accepts_future_identifiers() -> None:
    expected = {
        "flood",
        "tropical_cyclone",
        "severe_storm",
        "wildfire",
        "heatwave",
        "drought",
        "earthquake",
        "landslide",
        "glacial_lake_outburst_flood",
    }
    assert set(HAZARD_TAXONOMY) == expected

    for identifier in expected | {"volcanic_ashfall"}:
        assert TypeAdapter(HazardIdentifier).validate_python(identifier) == identifier
    with pytest.raises(ValidationError):
        CanonicalEnvironmentalRecord(
            record_type="observation",
            hazard_type="Flood",
            source=CanonicalSource(provider="fixture"),
            quality_status="UNVERIFIED",
            payload=ObservationPayload(measurement_basis="unknown"),
        )


def test_weather_normalization_preserves_raw_values_units_and_point_provenance() -> None:
    record = normalize_weather_record(
        {
            "id": 8,
            "provider": "Open-Meteo",
            "station_id": "internal-point",
            "station_name": "Global test point",
            "latitude": 10.0,
            "longitude": 20.0,
            "provider_latitude": 10.01,
            "provider_longitude": 20.01,
            "requested_latitude": 10.0,
            "requested_longitude": 20.0,
            "observation_time": datetime(2026, 11, 12, 10, tzinfo=timezone.utc),
            "fetched_at": datetime(2026, 11, 12, 10, 5, tzinfo=timezone.utc),
            "created_at": datetime(2026, 11, 12, 10, 6, tzinfo=timezone.utc),
            "freshness_status": "READY",
            "quality_status": "VALIDATED_SHAPE",
            "validation_findings": [],
            "values": {
                "temperature_c": 20.0,
                "humidity_percent": 60.0,
                "precipitation_mm": 1.5,
                "rain_mm": 1.0,
                "wind_speed_kmh": 7.2,
                "pressure_hpa": 1012.0,
                "source_value_column": "River Water Level Telemetry Hourly (meter)",
            },
            "provider_metadata": {
                "timezone": "UTC",
                "source_timezone": "UTC",
                "timezone_assumption": None,
                "source_timestamp_raw": "2026-11-12T10:00",
                "current_units": {
                    "temperature_2m": "°C",
                    "relative_humidity_2m": "%",
                    "precipitation": "mm",
                    "rain": "mm",
                    "wind_speed_10m": "km/h",
                    "surface_pressure": "hPa",
                },
                "source_current": {
                    "temperature_2m": 20,
                    "relative_humidity_2m": 60,
                    "precipitation": 1.5,
                    "rain": 1,
                    "wind_speed_10m": 7.2,
                    "surface_pressure": 1012,
                },
                "access_token": "must-not-be-retained",
            },
        }
    )

    assert record.contract_version == "1.0"
    assert record.local_record_id == 8
    assert record.source.source_record_id is None
    assert record.source.source_metadata.get("access_token") is None
    assert record.quality_status == "INCOMPLETE_METADATA"
    assert record.payload.measurement_basis == "model_derived"
    assert record.timestamps.source_timestamp_raw == "2026-11-12T10:00"
    assert record.timestamps.observation_time_utc == datetime(2026, 11, 12, 10, tzinfo=timezone.utc)
    assert record.timestamps.retrieval_time_utc == datetime(2026, 11, 12, 10, 5, tzinfo=timezone.utc)
    assert record.timestamps.observation_time_utc != record.timestamps.retrieval_time_utc
    assert record.geography.requested_coordinates == WGS84Point(latitude=10, longitude=20)
    assert record.geography.provider_returned_coordinates == WGS84Point(latitude=10.01, longitude=20.01)
    temperature = next(item for item in record.payload.measurements if item.name == "temperature_c")
    assert temperature.source_value == 20
    assert temperature.source_unit == "°C"
    assert temperature.normalized_value == 20
    assert temperature.normalized_unit == "°C"


def test_weather_provider_error_is_not_mislabeled_as_invalid_freshness() -> None:
    record = normalize_weather_record(
        {
            "provider": "Open-Meteo",
            "latitude": 10,
            "longitude": 20,
            "observation_time": datetime(2026, 11, 12, 10, tzinfo=timezone.utc),
            "fetched_at": datetime(2026, 11, 12, 10, 5, tzinfo=timezone.utc),
            "freshness_status": "ERROR",
            "quality_status": "INVALID",
            "validation_findings": ["Observation timestamp is more than five minutes in the future."],
            "values": {"temperature_c": 20},
        }
    )

    assert record.quality_status == "INVALID"
    assert record.freshness_status == "UNAVAILABLE"
    assert record.availability_status == "ERROR"


def test_legacy_weather_metadata_stays_incomplete_without_fabricated_source_time() -> None:
    record = normalize_weather_record(
        {
            "record_id": 1,
            "provider": "Open-Meteo",
            "latitude": 0,
            "longitude": 180,
            "observation_time": datetime(2026, 1, 1, tzinfo=timezone.utc),
            "fetched_at": datetime(2026, 1, 1, 0, 5, tzinfo=timezone.utc),
            "freshness_status": "READY",
            "quality_status": "VALIDATED_SHAPE",
            "values": {"temperature_c": 20},
            "raw_source_values": {"provider_source": "open-meteo", "timezone": None},
        }
    )
    assert record.timestamps.source_timestamp_raw is None
    assert record.quality_status == "INCOMPLETE_METADATA"
    assert next(item for item in record.payload.measurements if item.name == "temperature_c").source_value == 20
    assert any("Original provider timestamp" in item for item in record.validation_errors)


def test_hydrology_provenance_is_regional_and_missing_timezone_is_not_inferred() -> None:
    record = normalize_hydrology_record(
        {
            "record_id": 9,
            "provider": "NWDP/NWIC CWC",
            "source_resource_id": "resource-krishna",
            "source_record_id": 123,
            "station_id": "generated-key",
            "station_name": "Gauge",
            "latitude": 16.5,
            "longitude": 80.6,
            "observation_time": datetime(2026, 11, 12, 4, 30, tzinfo=timezone.utc),
            "fetched_at": datetime(2026, 11, 12, 5, tzinfo=timezone.utc),
            "freshness_status": "READY",
            "quality_status": "UNVERIFIED",
            "values": {"water_level": 2.4, "discharge": None, "rainfall": None},
            "geographic_metadata": {"station_id": "generated-key", "station_id_is_internal": True},
            "raw_source_values": {
                "source_resource_id": "resource-krishna",
                "source_record": {"River Water Level Telemetry Hourly (meter)": "2.4"},
                "source_timestamp_raw": "12-11-2026 10:00",
                "source_value_column": "River Water Level Telemetry Hourly (meter)",
            },
        }
    )
    assert record.source.source_record_id == 123
    assert record.source.source_dataset_id == "resource-krishna"
    assert record.timestamps.source_timestamp_raw == "12-11-2026 10:00"
    assert record.timestamps.source_timezone is None
    assert record.timestamps.timezone_assumption is None
    assert record.quality_status == "INCOMPLETE_METADATA"
    assert record.availability_status == "REGIONAL"
    assert record.geography.coverage_verified is False
    assert record.geography.station_id_is_internal is True
    assert any("Timezone" in item for item in record.validation_errors)
    level = record.payload.measurements[0]
    assert level.source_value == 2.4
    assert level.source_unit == "m"
    assert level.normalized_value == 2.4


def test_stale_records_remain_stale_and_missing_measurements_remain_null() -> None:
    record = normalize_weather_record(
        {
            "provider": "Open-Meteo",
            "latitude": 0,
            "longitude": 0,
            "observation_time": datetime(2020, 1, 1, tzinfo=timezone.utc),
            "fetched_at": datetime(2020, 1, 1, 0, 5, tzinfo=timezone.utc),
            "freshness_status": "STALE",
            "quality_status": "PARTIAL",
            "values": {"temperature_c": None},
            "provider_metadata": {},
        }
    )
    temperature = next(item for item in record.payload.measurements if item.name == "temperature_c")
    assert record.quality_status == "STALE"
    assert record.freshness_status == "STALE"
    assert record.availability_status == "STALE"
    assert temperature.source_value is None
    assert temperature.normalized_value is None
    assert record.timestamps.observation_time_utc == datetime(2020, 1, 1, tzinfo=timezone.utc)


def test_satellite_record_separates_acquisition_and_retrieval_without_item_pinning() -> None:
    acquired = datetime(2026, 11, 10, 5, 42, tzinfo=timezone.utc)
    retrieved = datetime(2026, 11, 12, 8, 31, tzinfo=timezone.utc)
    record = normalize_satellite_acquisition(
        provider="Copernicus Data Space",
        collection="sentinel-2-l2a",
        catalog_item_id="fixture-scene",
        acquisition_time=acquired,
        retrieved_at=retrieved,
        requested_bbox=(170, -10, -170, 10),
        source_bbox=(169, -11, -169, 11),
        process_result_pinned_to_catalog_item=False,
        bands=["B04", "B03", "B02"],
    )
    assert record.record_type == "satellite_acquisition"
    assert record.quality_status == "UNVERIFIED"
    assert record.availability_status == "UNVERIFIED"
    assert record.timestamps.acquisition_time_utc == acquired
    assert record.timestamps.retrieval_time_utc == retrieved
    assert record.geography.requested_bbox.crosses_antimeridian is True
    assert record.payload.process_result_pinned_to_catalog_item is False
    assert any("not demonstrably pinned" in item for item in record.validation_errors)


def test_forecast_contract_keeps_forecast_times_separate_from_observation_time() -> None:
    issue = datetime(2026, 11, 12, 0, tzinfo=timezone.utc)
    valid = datetime(2026, 11, 12, 6, tzinfo=timezone.utc)
    record = CanonicalEnvironmentalRecord(
        record_type="forecast",
        hazard_type="flood",
        source=CanonicalSource(provider="fixture provider"),
        timestamps=CanonicalTimestamps(
            forecast_issue_time_utc=issue,
            forecast_valid_time_utc=valid,
            forecast_lead_seconds=21600,
        ),
        quality_status="UNVERIFIED",
        payload=ForecastPayload(model_or_product="fixture"),
    )
    assert record.timestamps.observation_time_utc is None
    assert record.timestamps.forecast_issue_time_utc == issue
    assert record.timestamps.forecast_valid_time_utc == valid

    missing_times = CanonicalEnvironmentalRecord(
        record_type="forecast",
        source=CanonicalSource(provider="fixture provider"),
        quality_status="INCOMPLETE_METADATA",
        payload=ForecastPayload(),
    )
    assert len(missing_times.validation_errors) == 2
