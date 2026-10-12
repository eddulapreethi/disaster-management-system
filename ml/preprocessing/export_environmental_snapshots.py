from __future__ import annotations

import csv
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

WEATHER_COLUMNS = (
    "station_id",
    "station_name",
    "source",
    "latitude",
    "longitude",
    "observation_time",
    "fetched_at",
    "temperature_c",
    "humidity_percent",
    "precipitation_mm",
    "rain_mm",
    "wind_speed_kmh",
    "pressure_hpa",
)
HYDROLOGY_COLUMNS = (
    "source",
    "source_resource_id",
    "source_record_id",
    "station_id",
    "station_name",
    "river_name",
    "state_name",
    "district_name",
    "latitude",
    "longitude",
    "observation_time",
    "fetched_at",
    "water_level",
    "discharge",
    "rainfall",
)
WEATHER_DEFINITIONS = {
    "temperature_c": ("Provider-reported current air temperature.", "degC"),
    "humidity_percent": ("Provider-reported relative humidity.", "%"),
    "precipitation_mm": ("Open-Meteo current precipitation field.", "mm"),
    "rain_mm": ("Open-Meteo current rain field.", "mm"),
    "wind_speed_kmh": ("Provider-reported 10 m wind speed.", "km/h"),
    "pressure_hpa": ("Provider-reported surface pressure.", "hPa"),
    "latitude": ("Configured point latitude.", "decimal degrees, WGS 84"),
    "longitude": ("Configured point longitude.", "decimal degrees, WGS 84"),
    "observation_time": ("Provider observation timestamp; stored as UTC.", "UTC"),
    "fetched_at": ("Backend retrieval timestamp; stored as UTC.", "UTC"),
}
HYDROLOGY_DEFINITIONS = {
    "water_level": ("CWC river water level telemetry measurement.", "m"),
    "rainfall": ("CWC telemetry rainfall measurement.", "mm"),
    "discharge": ("No measured discharge value is supplied by the configured resource.", "not available"),
    "latitude": ("Provider station latitude.", "decimal degrees, WGS 84"),
    "longitude": ("Provider station longitude.", "decimal degrees, WGS 84"),
    "observation_time": ("Data Acquisition Time interpreted in configured source timezone, converted to UTC.", "UTC"),
    "fetched_at": ("Backend retrieval timestamp; stored as UTC.", "UTC"),
}


def _utc(value: Any) -> str | None:
    if value is None:
        return None
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _column_definitions(columns: tuple[str, ...], definitions: dict[str, tuple[str, str]]) -> list[dict[str, str]]:
    return [
        {
            "name": name,
            "definition": definitions.get(name, ("Stored source metadata; no transformation applied.", "source-defined"))[0],
            "unit": definitions.get(name, ("", "source-defined"))[1],
        }
        for name in columns
    ]


def write_snapshot(
    rows: list[dict[str, Any]],
    *,
    output_path: Path,
    dataset_name: str,
    source_name: str,
    source_url: str,
    columns: tuple[str, ...],
    definitions: dict[str, tuple[str, str]],
    temporal_resolution: str,
) -> dict[str, Any]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    source_row_count = len(rows)
    ordered_rows = sorted(
        rows,
        key=lambda row: (
            str(row.get("observation_time") or ""),
            str(row.get("station_id") or ""),
            str(row.get("source") or ""),
        ),
    )
    seen: set[tuple[str, str, str]] = set()
    duplicate_count = 0
    invalid_timestamp_count = 0
    invalid_coordinate_count = 0
    rows = []
    for row in ordered_rows:
        observation_time = _utc(row.get("observation_time"))
        fetched_at = _utc(row.get("fetched_at"))
        if observation_time is None or fetched_at is None:
            invalid_timestamp_count += 1
            continue
        key = (str(row.get("station_id") or ""), observation_time, str(row.get("source") or ""))
        if key in seen:
            duplicate_count += 1
            continue
        seen.add(key)
        latitude, longitude = row.get("latitude"), row.get("longitude")
        if (
            latitude is None
            or longitude is None
            or not math.isfinite(float(latitude))
            or not math.isfinite(float(longitude))
            or not -90 <= float(latitude) <= 90
            or not -180 <= float(longitude) <= 180
        ):
            invalid_coordinate_count += 1
            continue
        rows.append({**row, "observation_time": observation_time, "fetched_at": fetched_at})
    valid_coordinates = []
    observation_times = []
    retrieval_times = []
    missing_values = {column: 0 for column in columns}

    with output_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            normalized = dict(row)
            normalized["observation_time"] = row["observation_time"]
            normalized["fetched_at"] = row["fetched_at"]
            for column in columns:
                if normalized.get(column) is None:
                    missing_values[column] += 1
            if row.get("latitude") is not None and row.get("longitude") is not None:
                valid_coordinates.append((float(row["longitude"]), float(row["latitude"])))
            if normalized["observation_time"]:
                observation_times.append(normalized["observation_time"])
            if normalized["fetched_at"]:
                retrieval_times.append(normalized["fetched_at"])
            writer.writerow({column: normalized.get(column) for column in columns})

    output_bytes = output_path.read_bytes()
    bounds = (
        {
            "west": min(point[0] for point in valid_coordinates),
            "south": min(point[1] for point in valid_coordinates),
            "east": max(point[0] for point in valid_coordinates),
            "north": max(point[1] for point in valid_coordinates),
        }
        if valid_coordinates
        else None
    )
    manifest = {
        "manifest_version": "1.0",
        "dataset_name": dataset_name,
        "dataset_version": "1",
        "source_name": source_name,
        "source_url": source_url,
        "license": "Provider redistribution/license terms were not verified; do not redistribute this export without confirming them.",
        "retrieval_date": max(retrieval_times)[:10] if retrieval_times else None,
        "observation_date_range": {
            "start": min(observation_times) if observation_times else None,
            "end": max(observation_times) if observation_times else None,
        },
        "geographic_coverage": bounds,
        "spatial_resolution": "Station or configured point coordinates; not a continuous gridded surface.",
        "temporal_resolution": temporal_resolution,
        "columns": _column_definitions(columns, definitions),
        "row_count": len(rows),
        "source_row_count": source_row_count,
        "column_count": len(columns),
        "missing_values": missing_values,
        "validation": {
            "non_empty": bool(rows),
            "duplicate_station_observation_source_rows": duplicate_count,
            "invalid_timestamp_rows": invalid_timestamp_count,
            "invalid_coordinate_rows": invalid_coordinate_count,
            "valid_coordinate_rows": len(valid_coordinates),
            "excluded_rows": duplicate_count + invalid_timestamp_count + invalid_coordinate_count,
            "validation_passed": (
                bool(rows)
                and invalid_timestamp_count == 0
                and invalid_coordinate_count == 0
                and len(valid_coordinates) == len(rows)
            ),
        },
        "processing_version": "environmental-snapshot-export-v1",
        "dataset_sha256": hashlib.sha256(output_bytes).hexdigest(),
        "training_suitable": False,
        "training_limitation": (
            "Observations have no verified event labels or validated mapping to the legacy 20-index flood feature schema."
        ),
    }
    manifest_path = output_path.with_suffix(".manifest.json")
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return manifest


def export_observation_snapshots(db: Any, output_root: Path | None = None) -> dict[str, dict[str, Any]]:
    from sqlalchemy import select

    from app.models.hydrological_observation import HydrologicalObservation
    from app.models.weather_observation import WeatherObservation

    root = output_root or PROJECT_ROOT / "ml" / "datasets"
    weather_rows = [
        {column: getattr(row, column) for column in WEATHER_COLUMNS}
        for row in db.scalars(
            select(WeatherObservation).order_by(
                WeatherObservation.observation_time,
                WeatherObservation.station_id,
                WeatherObservation.id,
            )
        ).all()
    ]
    hydrology_rows = [
        {column: getattr(row, column) for column in HYDROLOGY_COLUMNS}
        for row in db.scalars(
            select(HydrologicalObservation).order_by(
                HydrologicalObservation.observation_time,
                HydrologicalObservation.station_id,
                HydrologicalObservation.source,
                HydrologicalObservation.id,
            )
        ).all()
    ]
    weather = write_snapshot(
        weather_rows,
        output_path=root / "weather" / "processed" / "weather_observations.csv",
        dataset_name="DisasterGuard weather observations",
        source_name="Open-Meteo",
        source_url="https://api.open-meteo.com/v1/forecast",
        columns=WEATHER_COLUMNS,
        definitions=WEATHER_DEFINITIONS,
        temporal_resolution="Provider current observation timestamps; update cadence varies by variable/location.",
    )
    hydrology = write_snapshot(
        hydrology_rows,
        output_path=root / "hydrological" / "processed" / "hydrology_observations.csv",
        dataset_name="DisasterGuard CWC/NWDP hydrology observations",
        source_name="NWDP CKAN datastore; configured public CWC resources",
        source_url="https://nwdp.nwic.gov.in/api/3/action/datastore_search",
        columns=HYDROLOGY_COLUMNS,
        definitions=HYDROLOGY_DEFINITIONS,
        temporal_resolution="Hourly telemetry resource labels; actual observed publication can be delayed.",
    )
    return {"weather": weather, "hydrology": hydrology}


def main() -> None:
    from app.database.database import SessionLocal

    with SessionLocal() as db:
        manifests = export_observation_snapshots(db)
    print(
        json.dumps(
            {
                name: {
                    "row_count": manifest["row_count"],
                    "dataset_sha256": manifest["dataset_sha256"],
                    "training_suitable": manifest["training_suitable"],
                }
                for name, manifest in manifests.items()
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
