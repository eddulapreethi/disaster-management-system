from __future__ import annotations

import hashlib
import json
import sys
from unittest.mock import Mock

import pytest

from ml.preprocessing import acquire_open_meteo_archive as acquisition
from ml.preprocessing.acquire_open_meteo_archive import (
    DEFAULT_OUTPUT,
    EXPECTED_UNITS,
    acquire_archive,
    validate_archive_payload,
)
from ml.preprocessing.flood_environmental_dataset import DEFAULT_RAW
from ml.preprocessing.flood_target_readiness import get_flood_target_readiness


def archive_payload() -> dict:
    return {
        "latitude": 9.95,
        "longitude": 76.30,
        "timezone": "GMT",
        "utc_offset_seconds": 0,
        "daily_units": EXPECTED_UNITS.copy(),
        "daily": {
            "time": ["2024-01-01", "2024-01-02"],
            "temperature_2m_mean": [27.0, 28.0],
            "precipitation_sum": [0.0, 2.5],
            "rain_sum": [0.0, 2.5],
            "wind_speed_10m_max": [12.0, 15.0],
            "relative_humidity_2m_mean": [80, 82],
        },
    }


def test_archive_payload_requires_units_and_aligned_daily_series() -> None:
    payload = archive_payload()
    assert validate_archive_payload(payload)["daily"]["time"] == ["2024-01-01", "2024-01-02"]

    payload["daily"]["rain_sum"] = [0.0]
    with pytest.raises(ValueError, match="misaligned rain_sum"):
        validate_archive_payload(payload)

    payload = archive_payload()
    payload["daily_units"]["precipitation_sum"] = "in"
    with pytest.raises(ValueError, match="expected 'mm'"):
        validate_archive_payload(payload)


def test_archive_acquisition_writes_hashed_source_and_protects_existing_file(tmp_path) -> None:
    raw_file = tmp_path / "archive.json"
    response = Mock()
    response.json.return_value = archive_payload()
    response.content = json.dumps(archive_payload(), separators=(",", ":")).encode()
    client = Mock()
    client.get.return_value = response

    manifest = acquire_archive("2024-01-01", "2024-01-02", raw_file, session=client)

    assert raw_file.read_bytes() == response.content
    assert manifest["retrieved_file_sha256"] == hashlib.sha256(response.content).hexdigest()
    assert manifest["requested_location_wgs84"] == {"latitude": 9.9312, "longitude": 76.2673}
    assert manifest["returned_grid_location_wgs84"] == {"latitude": 9.95, "longitude": 76.3}
    assert manifest["requested_date_range"] == {"start": "2024-01-01", "end": "2024-01-02"}
    assert manifest["requested_timezone"] == "UTC"
    assert manifest["returned_timezone"] == "GMT"
    assert manifest["daily_units"] == EXPECTED_UNITS
    assert manifest["row_count"] == 2
    assert manifest["provider_returned_model"] == "UNAVAILABLE_IN_RESPONSE"
    assert manifest["provider_returned_spatial_resolution"] == "UNAVAILABLE_IN_RESPONSE"
    assert manifest["licensing_evidence_status"] == "NOT_VERIFIED"
    assert client.get.call_args.args[0] == acquisition.ARCHIVE_URL
    assert client.get.call_args.kwargs["params"]["latitude"] == 9.9312
    assert client.get.call_args.kwargs["params"]["longitude"] == 76.2673
    assert json.loads(raw_file.with_suffix(".manifest.json").read_text()) == manifest
    client.get.assert_called_once()
    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        acquire_archive("2024-01-01", "2024-01-02", raw_file, session=client)
    assert client.get.call_count == 1


def test_default_output_matches_flood_readiness_archive_path() -> None:
    project_root = acquisition.PROJECT_ROOT
    expected_path = (
        project_root / "ml" / "datasets" / "raw_sources" / "open_meteo" / "archive.json"
    )

    assert DEFAULT_OUTPUT == expected_path
    assert DEFAULT_RAW == expected_path


def test_custom_coordinates_are_requested_and_kept_separate_from_provider_grid(
    tmp_path,
) -> None:
    raw_file = tmp_path / "custom-location.json"
    payload = archive_payload()
    payload["latitude"] = 10.1
    payload["longitude"] = 76.5
    response = Mock()
    response.json.return_value = payload
    response.content = json.dumps(payload, separators=(",", ":")).encode()
    client = Mock()
    client.get.return_value = response

    manifest = acquire_archive(
        "2024-01-01",
        "2024-01-02",
        raw_file,
        latitude=10.05,
        longitude=76.45,
        session=client,
    )

    assert client.get.call_args.kwargs["params"]["latitude"] == 10.05
    assert client.get.call_args.kwargs["params"]["longitude"] == 76.45
    assert manifest["requested_location_wgs84"] == {"latitude": 10.05, "longitude": 76.45}
    assert manifest["returned_grid_location_wgs84"] == {"latitude": 10.1, "longitude": 76.5}
    assert manifest["requested_location_wgs84"] != manifest["returned_grid_location_wgs84"]


def test_provider_model_and_resolution_are_recorded_only_when_returned(tmp_path) -> None:
    payload = archive_payload()
    payload["model"] = "provider-returned-model"
    payload["spatial_resolution"] = "provider-returned-resolution"
    response = Mock()
    response.json.return_value = payload
    response.content = json.dumps(payload, separators=(",", ":")).encode()
    client = Mock()
    client.get.return_value = response

    manifest = acquire_archive(
        "2024-01-01",
        "2024-01-02",
        tmp_path / "archive.json",
        session=client,
    )

    assert manifest["provider_returned_model"] == "provider-returned-model"
    assert manifest["provider_returned_spatial_resolution"] == "provider-returned-resolution"


def test_non_default_location_requires_explicit_output_before_network_access() -> None:
    client = Mock()

    with pytest.raises(ValueError, match="explicit output path"):
        acquire_archive(
            "2024-01-01",
            "2024-01-02",
            latitude=10.05,
            longitude=76.45,
            session=client,
        )

    client.get.assert_not_called()


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [
        (float("nan"), 76.0),
        (9.0, float("inf")),
        (-91.0, 76.0),
        (9.0, 181.0),
        (True, 76.0),
    ],
)
def test_invalid_coordinates_are_rejected_before_network_access(
    tmp_path,
    latitude,
    longitude,
) -> None:
    client = Mock()

    with pytest.raises(ValueError, match="coordinates"):
        acquire_archive(
            "2024-01-01",
            "2024-01-02",
            tmp_path / "archive.json",
            latitude=latitude,
            longitude=longitude,
            session=client,
        )

    client.get.assert_not_called()


def test_manifest_file_alone_is_not_overwritten_without_force(tmp_path) -> None:
    raw_file = tmp_path / "archive.json"
    raw_file.with_suffix(".manifest.json").write_text("existing", encoding="utf-8")
    client = Mock()

    with pytest.raises(FileExistsError, match="archive or manifest"):
        acquire_archive("2024-01-01", "2024-01-02", raw_file, session=client)

    client.get.assert_not_called()


def test_cli_accepts_custom_coordinates_and_explicit_output(
    monkeypatch,
    tmp_path,
) -> None:
    output = tmp_path / "reviewed-gauge-weather.json"
    captured = {}
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "acquire_open_meteo_archive",
            "--start-date",
            "2020-01-01",
            "--end-date",
            "2024-12-31",
            "--latitude",
            "10.05",
            "--longitude",
            "76.45",
            "--output",
            str(output),
        ],
    )

    def fake_acquire(start_date, end_date, output_path, **kwargs):
        captured.update(
            start_date=start_date,
            end_date=end_date,
            output_path=output_path,
            **kwargs,
        )
        return {
            "row_count": 1,
            "observation_date_range": {"start": start_date, "end": end_date},
            "returned_grid_location_wgs84": {"latitude": 10.1, "longitude": 76.5},
            "retrieved_file_sha256": "test-hash",
        }

    monkeypatch.setattr(acquisition, "acquire_archive", fake_acquire)

    acquisition.main()

    assert captured == {
        "start_date": "2020-01-01",
        "end_date": "2024-12-31",
        "output_path": output,
        "latitude": 10.05,
        "longitude": 76.45,
        "force": False,
    }


def test_cli_preserves_kochI_defaults_when_coordinates_are_omitted(
    monkeypatch,
) -> None:
    captured = {}
    monkeypatch.setattr(
        sys,
        "argv",
        ["acquire_open_meteo_archive"],
    )

    def fake_acquire(start_date, end_date, output_path, **kwargs):
        captured.update(
            start_date=start_date,
            end_date=end_date,
            output_path=output_path,
            **kwargs,
        )
        return {
            "row_count": 1,
            "observation_date_range": {"start": start_date, "end": end_date},
            "returned_grid_location_wgs84": {"latitude": 9.95, "longitude": 76.3},
            "retrieved_file_sha256": "test-hash",
        }

    monkeypatch.setattr(acquisition, "acquire_archive", fake_acquire)

    acquisition.main()

    assert captured == {
        "start_date": "2020-01-01",
        "end_date": "2024-12-31",
        "output_path": None,
        "latitude": None,
        "longitude": None,
        "force": False,
    }


def test_acquired_archive_is_at_the_path_checked_by_readiness(
    tmp_path,
    monkeypatch,
) -> None:
    payload = archive_payload()
    response = Mock()
    response.json.return_value = payload
    response.content = json.dumps(payload, separators=(",", ":")).encode()
    client = Mock()
    client.get.return_value = response
    output_path = (
        tmp_path / "ml" / "datasets" / "raw_sources" / "open_meteo" / "archive.json"
    )
    acquire_archive(
        "2024-01-01",
        "2024-01-02",
        output_path,
        session=client,
    )
    readiness = get_flood_target_readiness(tmp_path)

    assert readiness["files"]["historical_weather_archive"]["path"].replace("\\", "/") == (
        "ml/datasets/raw_sources/open_meteo/archive.json"
    )
    assert readiness["files"]["weather_archive_manifest"]["path"].replace("\\", "/") == (
        "ml/datasets/raw_sources/open_meteo/archive.manifest.json"
    )
    assert readiness["files"]["historical_weather_archive"]["available"] is True
    assert readiness["files"]["weather_archive_manifest"]["available"] is True
    assert readiness["requirements"]["historical_weather_coverage"]["syntax_status"] == "VALID"
    assert readiness["status"] == "NOT_READY"

    output_path.write_text(output_path.read_text(encoding="utf-8") + " ", encoding="utf-8")
    tampered_readiness = get_flood_target_readiness(tmp_path)

    assert tampered_readiness["requirements"]["historical_weather_coverage"]["status"] == (
        "SYNTACTICALLY_INVALID"
    )
    assert "SHA-256 does not match" in tampered_readiness["requirements"][
        "historical_weather_coverage"
    ]["details"]
    assert tampered_readiness["status"] == "NOT_READY"


def test_archive_rejects_bad_date_range_without_request(tmp_path) -> None:
    client = Mock()
    with pytest.raises(ValueError, match="on or after"):
        acquire_archive("2024-01-02", "2024-01-01", tmp_path / "archive.json", session=client)
    client.get.assert_not_called()
