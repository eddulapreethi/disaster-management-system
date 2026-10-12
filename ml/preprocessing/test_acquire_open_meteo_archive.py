from __future__ import annotations

import hashlib
import json
from unittest.mock import Mock

import pytest

from ml.preprocessing.acquire_open_meteo_archive import (
    EXPECTED_UNITS,
    acquire_archive,
    validate_archive_payload,
)


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
    assert json.loads(raw_file.with_suffix(".manifest.json").read_text()) == manifest
    client.get.assert_called_once()
    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        acquire_archive("2024-01-01", "2024-01-02", raw_file, session=client)


def test_archive_rejects_bad_date_range_without_request(tmp_path) -> None:
    client = Mock()
    with pytest.raises(ValueError, match="on or after"):
        acquire_archive("2024-01-02", "2024-01-01", tmp_path / "archive.json", session=client)
    client.get.assert_not_called()
