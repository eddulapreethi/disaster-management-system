import json
from datetime import datetime, timezone

from ml.preprocessing.export_environmental_snapshots import write_snapshot


def test_environmental_export_is_deduplicated_and_has_a_stable_manifest(tmp_path) -> None:
    observation = {
        "station_id": "kochi",
        "station_name": "Kochi",
        "source": "open-meteo",
        "latitude": 9.9312,
        "longitude": 76.2673,
        "observation_time": datetime(2026, 10, 11, 8, 30, tzinfo=timezone.utc),
        "fetched_at": datetime(2026, 10, 11, 8, 35, tzinfo=timezone.utc),
        "temperature_c": 29.9,
    }
    output = tmp_path / "weather.csv"

    manifest = write_snapshot(
        [observation, observation],
        output_path=output,
        dataset_name="Weather test observations",
        source_name="Open-Meteo",
        source_url="https://api.open-meteo.com/v1/forecast",
        columns=(
            "station_id",
            "station_name",
            "source",
            "latitude",
            "longitude",
            "observation_time",
            "fetched_at",
            "temperature_c",
        ),
        definitions={"temperature_c": ("Temperature.", "degC")},
        temporal_resolution="Provider timestamps",
    )
    repeated_manifest = write_snapshot(
        [observation, observation],
        output_path=output,
        dataset_name="Weather test observations",
        source_name="Open-Meteo",
        source_url="https://api.open-meteo.com/v1/forecast",
        columns=(
            "station_id",
            "station_name",
            "source",
            "latitude",
            "longitude",
            "observation_time",
            "fetched_at",
            "temperature_c",
        ),
        definitions={"temperature_c": ("Temperature.", "degC")},
        temporal_resolution="Provider timestamps",
    )
    saved_manifest = json.loads(output.with_suffix(".manifest.json").read_text(encoding="utf-8"))

    assert manifest["row_count"] == 1
    assert manifest["validation"]["duplicate_station_observation_source_rows"] == 1
    assert manifest["validation"]["validation_passed"] is True
    assert manifest["training_suitable"] is False
    assert manifest["dataset_sha256"] == repeated_manifest["dataset_sha256"]
    assert saved_manifest == repeated_manifest
