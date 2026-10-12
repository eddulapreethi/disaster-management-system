from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "datasets"
    / "weather"
    / "raw"
    / "open_meteo_koch_2020-2024_best_match.json"
)
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
REQUESTED_LOCATION = {"latitude": 9.9312, "longitude": 76.2673}
DAILY_VARIABLES = (
    "temperature_2m_mean",
    "precipitation_sum",
    "rain_sum",
    "wind_speed_10m_max",
    "relative_humidity_2m_mean",
)
EXPECTED_UNITS = {
    "temperature_2m_mean": f"{chr(176)}C",
    "precipitation_sum": "mm",
    "rain_sum": "mm",
    "wind_speed_10m_max": "km/h",
    "relative_humidity_2m_mean": "%",
}


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def validate_archive_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Open-Meteo archive response must be a JSON object.")
    try:
        latitude = float(payload["latitude"])
        longitude = float(payload["longitude"])
        daily = payload["daily"]
        units = payload["daily_units"]
        dates = daily["time"]
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("Open-Meteo response is missing coordinates or daily data.") from error
    if not isinstance(daily, dict) or not isinstance(units, dict) or not isinstance(dates, list) or not dates:
        raise ValueError("Open-Meteo daily data must contain a non-empty time axis.")
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError("Open-Meteo returned coordinates outside WGS 84 bounds.")
    if payload.get("timezone") not in {"GMT", "UTC"} or payload.get("utc_offset_seconds") != 0:
        raise ValueError("Open-Meteo daily archive must be returned in UTC.")
    for variable, unit in EXPECTED_UNITS.items():
        if variable not in daily or len(daily[variable]) != len(dates):
            raise ValueError(f"Open-Meteo response has a missing or misaligned {variable} series.")
        if units.get(variable) != unit:
            raise ValueError(
                f"Open-Meteo returned {variable} in {units.get(variable)!r}; expected {unit!r}."
            )
    return payload


def acquire_archive(
    start_date: str,
    end_date: str,
    output_path: str | Path = DEFAULT_OUTPUT,
    *,
    force: bool = False,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    from datetime import date

    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    if end < start:
        raise ValueError("end_date must be on or after start_date.")
    target = Path(output_path)
    manifest_path = target.with_suffix(".manifest.json")
    if target.exists() and not force:
        raise FileExistsError(f"Refusing to overwrite existing source data: {target}. Use --force explicitly.")
    params = {
        **REQUESTED_LOCATION,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "daily": ",".join(DAILY_VARIABLES),
        "timezone": "UTC",
        "models": "best_match",
    }
    client = session or requests.Session()
    response = client.get(ARCHIVE_URL, params=params, timeout=(10, 120))
    response.raise_for_status()
    payload = validate_archive_payload(response.json())
    raw_bytes = response.content

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw_bytes)
    manifest = {
        "manifest_version": "1.0",
        "dataset_name": "Open-Meteo historical daily weather at configured Kochi point",
        "source_name": "Open-Meteo Historical Weather API",
        "source_url": ARCHIVE_URL,
        "request_parameters": params,
        "model_selection": (
            "best_match; the provider-selected model is not included in the response and may vary "
            "by variable or period"
        ),
        "requested_location_wgs84": REQUESTED_LOCATION,
        "returned_grid_location_wgs84": {
            "latitude": payload["latitude"],
            "longitude": payload["longitude"],
        },
        "spatial_resolution": (
            "Provider-selected gridded reanalysis point; exact native resolution/model is not returned. "
            "This is not a point-station measurement."
        ),
        "temporal_resolution": "Daily UTC aggregates",
        "observation_date_range": {
            "start": payload["daily"]["time"][0],
            "end": payload["daily"]["time"][-1],
        },
        "row_count": len(payload["daily"]["time"]),
        "columns": [
            {"name": "time", "definition": "UTC date of daily aggregate.", "unit": "YYYY-MM-DD UTC"},
            *[
                {
                    "name": variable,
                    "definition": f"Open-Meteo daily archive variable {variable}.",
                    "unit": EXPECTED_UNITS[variable],
                }
                for variable in DAILY_VARIABLES
            ],
        ],
        "license": (
            "Open-Meteo API terms and the provider-selected underlying model's attribution/redistribution "
            "terms must be checked before redistribution; this pipeline does not assert a license."
        ),
        "retrieved_file": target.name,
        "retrieved_file_sha256": _sha256(raw_bytes),
        "training_suitable": False,
        "limitation": (
            "Environmental predictors only: no flood labels, event-negative coverage, or approved target "
            "definition is included."
        ),
    }
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=False, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Acquire real daily Open-Meteo historical weather for Kochi.")
    parser.add_argument("--start-date", default="2020-01-01")
    parser.add_argument("--end-date", default="2024-12-31")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--force", action="store_true", help="Explicitly replace an existing raw source file.")
    args = parser.parse_args()
    try:
        manifest = acquire_archive(args.start_date, args.end_date, args.output, force=args.force)
    except (OSError, ValueError, requests.RequestException) as error:
        parser.error(str(error))
    print(
        json.dumps(
            {
                "output": str(args.output),
                "rows": manifest["row_count"],
                "dates": manifest["observation_date_range"],
                "returned_grid_location_wgs84": manifest["returned_grid_location_wgs84"],
                "sha256": manifest["retrieved_file_sha256"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
