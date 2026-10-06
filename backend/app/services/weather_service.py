import asyncio
import json
import logging
import math
import os
import re
import threading
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert

from app.database.database import SessionLocal
from app.models.weather_observation import WeatherObservation

DEFAULT_POLL_INTERVAL_SECONDS = 60
DEFAULT_MAX_AGE_SECONDS = 7200
RETENTION_DAYS = 30
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
DEFAULT_LOCATION = {"name": "Kochi", "latitude": 9.9312, "longitude": 76.2673}
logger = logging.getLogger(__name__)

_status_lock = threading.Lock()
_status: dict[str, Any] = {
    "enabled": False,
    "running": False,
    "interval_seconds": DEFAULT_POLL_INTERVAL_SECONDS,
    "last_cycle_started_at": None,
    "last_cycle_finished_at": None,
    "last_successful_fetch_at": None,
    "configured_locations": 0,
    "successful_locations": 0,
    "stored_observations": 0,
    "duplicates_skipped": 0,
    "failed_locations": [],
}


def get_poll_interval_seconds() -> int:
    try:
        interval = int(os.getenv("WEATHER_POLL_INTERVAL_SECONDS", str(DEFAULT_POLL_INTERVAL_SECONDS)))
    except ValueError as error:
        raise RuntimeError("WEATHER_POLL_INTERVAL_SECONDS must be a positive integer.") from error
    if interval < 1:
        raise RuntimeError("WEATHER_POLL_INTERVAL_SECONDS must be a positive integer.")
    return interval


def get_max_age_seconds() -> int:
    try:
        max_age = int(os.getenv("WEATHER_MAX_AGE_SECONDS", str(DEFAULT_MAX_AGE_SECONDS)))
    except ValueError as error:
        raise RuntimeError("WEATHER_MAX_AGE_SECONDS must be a positive integer.") from error
    if max_age < 1:
        raise RuntimeError("WEATHER_MAX_AGE_SECONDS must be a positive integer.")
    return max_age


def configured_locations() -> list[dict[str, float | str]]:
    """Read configured locations; use one configurable project location by default."""
    raw = os.getenv("WEATHER_LOCATIONS_JSON", "").strip()
    if not raw:
        location = {
            "name": os.getenv("WEATHER_LOCATION_NAME", DEFAULT_LOCATION["name"]).strip(),
            "latitude": os.getenv("WEATHER_LATITUDE", str(DEFAULT_LOCATION["latitude"])),
            "longitude": os.getenv("WEATHER_LONGITUDE", str(DEFAULT_LOCATION["longitude"])),
        }
        raw = json.dumps([location])
    try:
        locations = json.loads(raw)
    except json.JSONDecodeError as error:
        raise RuntimeError("WEATHER_LOCATIONS_JSON must be a JSON array of locations.") from error
    if not isinstance(locations, list) or not locations:
        raise RuntimeError("WEATHER_LOCATIONS_JSON must contain at least one location.")

    validated = []
    station_ids: set[str] = set()
    for location in locations:
        if not isinstance(location, dict):
            raise RuntimeError("Each weather location must be a JSON object.")
        name = str(location.get("name", "")).strip()
        try:
            latitude = float(location["latitude"])
            longitude = float(location["longitude"])
        except (KeyError, TypeError, ValueError) as error:
            raise RuntimeError("Each weather location needs numeric latitude and longitude.") from error
        if not name or not math.isfinite(latitude) or not -90 <= latitude <= 90:
            raise RuntimeError("Weather location name or latitude is invalid.")
        if not math.isfinite(longitude) or not -180 <= longitude <= 180:
            raise RuntimeError("Weather location longitude is invalid.")
        station_id = _station_id(name)
        if station_id in station_ids:
            raise RuntimeError(f"Weather location names must be unique after normalization: {name!r}.")
        station_ids.add(station_id)
        validated.append({"name": name, "latitude": latitude, "longitude": longitude})
    return validated


def _station_id(name: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return normalized or "location"


def _observation_key(station_id: str, observation_time: datetime, source: str) -> tuple[str, str, str]:
    return station_id, _as_utc(observation_time).isoformat(), source


def _parse_location_response(location: dict[str, float | str], payload: dict[str, Any]) -> dict[str, Any]:
    current = payload.get("current")
    if not isinstance(current, dict) or not current.get("time"):
        raise RuntimeError("Open-Meteo response did not include current observations.")

    requested_fields = (
        "temperature_2m",
        "relative_humidity_2m",
        "precipitation",
        "rain",
        "wind_speed_10m",
        "surface_pressure",
    )
    missing_fields = [field for field in requested_fields if field not in current]
    if missing_fields:
        raise RuntimeError(f"Open-Meteo response is missing requested fields: {', '.join(missing_fields)}.")

    try:
        observation_time = datetime.fromisoformat(str(current["time"]).replace("Z", "+00:00"))
    except ValueError as error:
        raise RuntimeError("Open-Meteo returned an invalid observation timestamp.") from error
    if observation_time.tzinfo is None:
        observation_time = observation_time.replace(tzinfo=timezone.utc)

    values = {
        "temperature_c": current.get("temperature_2m"),
        "humidity_percent": current.get("relative_humidity_2m"),
        "precipitation_mm": current.get("precipitation"),
        "rain_mm": current.get("rain"),
        "wind_speed_kmh": current.get("wind_speed_10m"),
        "pressure_hpa": current.get("surface_pressure"),
    }
    for key, value in values.items():
        if value is not None:
            try:
                number = float(value)
            except (TypeError, ValueError) as error:
                raise RuntimeError(f"Open-Meteo returned invalid {key}.") from error
            if not math.isfinite(number):
                raise RuntimeError(f"Open-Meteo returned non-finite {key}.")
            if key == "humidity_percent" and not 0 <= number <= 100:
                raise RuntimeError("Open-Meteo returned humidity outside 0-100 percent.")
            if key in {"precipitation_mm", "rain_mm", "wind_speed_kmh"} and number < 0:
                raise RuntimeError(f"Open-Meteo returned negative {key}.")
            if key == "pressure_hpa" and number <= 0:
                raise RuntimeError("Open-Meteo returned non-positive pressure.")
            values[key] = number

    return {
        "station_id": _station_id(str(location["name"])),
        "station_name": location["name"],
        "source": "open-meteo",
        "latitude": location["latitude"],
        "longitude": location["longitude"],
        "observation_time": observation_time,
        "fetched_at": datetime.now(timezone.utc),
        **values,
    }


def _fetch_batch(locations: list[dict[str, float | str]]) -> list[dict[str, Any]]:
    """Fetch many configured coordinates in one Open-Meteo API request."""
    query = urlencode(
        {
            "latitude": ",".join(str(location["latitude"]) for location in locations),
            "longitude": ",".join(str(location["longitude"]) for location in locations),
            "current": "temperature_2m,relative_humidity_2m,precipitation,rain,wind_speed_10m,surface_pressure",
            "timezone": "UTC",
        }
    )
    request = Request(
        f"{OPEN_METEO_URL}?{query}",
        headers={"User-Agent": "DisasterGuard-AI/1.0"},
    )
    try:
        with urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
        logger.warning("Weather source unavailable: %s", error)
        raise RuntimeError(f"Open-Meteo request failed: {error}") from error

    response_items = payload if isinstance(payload, list) else [payload]
    if len(response_items) != len(locations):
        raise RuntimeError(
            f"Open-Meteo returned {len(response_items)} locations for {len(locations)} requested coordinates."
        )
    return [_parse_location_response(location, item) for location, item in zip(locations, response_items, strict=True)]


def collect_weather_cycle() -> dict[str, Any]:
    """Poll Open-Meteo and persist only observations not already stored."""
    locations = configured_locations()
    interval = get_poll_interval_seconds()
    started_at = datetime.now(timezone.utc)
    with _status_lock:
        _status.update(
            running=True,
            interval_seconds=interval,
            last_cycle_started_at=started_at.isoformat(),
            configured_locations=len(locations),
            failed_locations=[],
        )

    records: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    try:
        records = _fetch_batch(locations)
    except Exception as error:
        logger.exception("Weather response validation or fetch failed.")
        failures = [{"location": str(location["name"]), "error": "Weather source request or response validation failed."} for location in locations]

    if failures:
        finished_at = datetime.now(timezone.utc)
        with _status_lock:
            _status.update(
                running=False,
                last_cycle_finished_at=finished_at.isoformat(),
                successful_locations=0,
                stored_observations=0,
                duplicates_skipped=0,
                failed_locations=failures,
            )
        return get_collector_status()

    unique_records: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str, str]] = set()
    for record in records:
        key = _observation_key(record["station_id"], record["observation_time"], record["source"])
        if key in seen_keys:
            continue
        seen_keys.add(key)
        unique_records.append(record)

    db = SessionLocal()
    inserted_count = 0
    try:
        if unique_records:
            statement_values = unique_records
            dialect_name = db.get_bind().dialect.name
            if dialect_name == "postgresql":
                statement = postgresql_insert(WeatherObservation).values(statement_values)
                statement = statement.on_conflict_do_nothing(
                    index_elements=["station_id", "observation_time", "source"]
                )
                inserted_count = db.execute(statement).rowcount or 0
            else:
                existing = db.execute(
                    select(
                        WeatherObservation.station_id,
                        WeatherObservation.observation_time,
                        WeatherObservation.source,
                    ).where(
                        WeatherObservation.station_id.in_({record["station_id"] for record in unique_records})
                    )
                ).all()
                existing_keys = {
                    _observation_key(row.station_id, row.observation_time, row.source)
                    for row in existing
                }
                pending = [
                    record for record in unique_records
                    if _observation_key(record["station_id"], record["observation_time"], record["source"]) not in existing_keys
                ]
                db.add_all(WeatherObservation(**record) for record in pending)
                inserted_count = len(pending)
        cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
        db.query(WeatherObservation).filter(WeatherObservation.fetched_at < cutoff).delete(synchronize_session=False)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Weather database error while storing observations.")
        finished_at = datetime.now(timezone.utc)
        with _status_lock:
            _status.update(
                running=False,
                last_cycle_finished_at=finished_at.isoformat(),
                failed_locations=[{"location": "database", "error": "Weather database operation failed."}],
            )
        raise
    finally:
        db.close()

    finished_at = datetime.now(timezone.utc)
    with _status_lock:
        _status.update(
            running=False,
            last_cycle_finished_at=finished_at.isoformat(),
            last_successful_fetch_at=finished_at.isoformat(),
            successful_locations=len(unique_records),
            stored_observations=inserted_count,
            duplicates_skipped=len(records) - inserted_count,
            failed_locations=failures,
        )
    logger.info(
        "Weather fetch successful: %s locations, %s new observations stored, %s duplicates skipped.",
        len(locations),
        inserted_count,
        len(records) - inserted_count,
    )
    if len(records) > inserted_count:
        logger.info("Weather observation skipped because it is already stored (%s duplicate(s)).", len(records) - inserted_count)
    return get_collector_status()


async def run_weather_collector() -> None:
    """Poll immediately and repeat at the configured interval until cancelled."""
    loop = asyncio.get_running_loop()
    next_cycle = loop.time()
    logger.info("Weather collector started.")
    with _status_lock:
        _status["enabled"] = True
    try:
        while True:
            try:
                await asyncio.to_thread(collect_weather_cycle)
            except Exception as error:
                logger.exception("Weather collector cycle failed; it will retry after the configured interval.")
                with _status_lock:
                    _status.update(
                        running=False,
                        last_cycle_finished_at=datetime.now(timezone.utc).isoformat(),
                        failed_locations=[{"location": "collector", "error": "Weather collector cycle failed; see backend logs."}],
                    )
            try:
                interval = get_poll_interval_seconds()
            except RuntimeError:
                logger.exception("Invalid weather poll interval; using the default interval until configuration is corrected.")
                interval = DEFAULT_POLL_INTERVAL_SECONDS
            next_cycle += interval
            await asyncio.sleep(max(0.0, next_cycle - loop.time()))
    finally:
        with _status_lock:
            _status["enabled"] = False
        logger.info("Weather collector stopped.")


def get_collector_status() -> dict[str, Any]:
    with _status_lock:
        return dict(_status)


def get_weather_status() -> dict[str, Any]:
    collector = get_collector_status()
    observations = get_latest_observations()
    now = datetime.now(timezone.utc)
    latest = max(observations, key=lambda row: _as_utc(row.observation_time), default=None)
    max_age_seconds = get_max_age_seconds()

    if latest is None:
        status = "ERROR" if collector.get("failed_locations") else "UNAVAILABLE"
        message = "The latest weather collection attempt failed." if status == "ERROR" else "No weather observation has been stored yet."
    elif collector.get("failed_locations"):
        status = "ERROR"
        message = "The latest weather collection attempt failed; the last stored observation is shown."
    elif now - _as_utc(latest.observation_time) > timedelta(seconds=max_age_seconds):
        status = "STALE"
        message = f"The latest stored observation is older than the {max_age_seconds}-second freshness window."
    else:
        status = "READY"
        message = "A recent, valid weather observation is stored in the database."

    return {
        "source": latest.source if latest else "open-meteo",
        "status": status,
        "message": message,
        "last_observation": latest.observation_time.isoformat() if latest else None,
        "last_checked": collector.get("last_cycle_finished_at"),
        "last_successful_fetch": collector.get("last_successful_fetch_at"),
        "max_age_seconds": max_age_seconds,
        "poll_interval_seconds": collector.get("interval_seconds", DEFAULT_POLL_INTERVAL_SECONDS),
        "collector": collector,
    }


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def get_latest_observations() -> list[WeatherObservation]:
    """Return one newest source observation for every station and source."""
    db = SessionLocal()
    try:
        ranked_observations = (
            select(
                WeatherObservation.id.label("observation_id"),
                func.row_number()
                .over(
                    partition_by=(WeatherObservation.station_id, WeatherObservation.source),
                    order_by=(WeatherObservation.observation_time.desc(), WeatherObservation.id.desc()),
                )
                .label("row_number"),
            )
            .subquery()
        )
        return list(
            db.scalars(
                select(WeatherObservation)
                .join(ranked_observations, WeatherObservation.id == ranked_observations.c.observation_id)
                .where(ranked_observations.c.row_number == 1)
                .order_by(WeatherObservation.station_name)
            ).all()
        )
    finally:
        db.close()
