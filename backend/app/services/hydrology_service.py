from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.database import SessionLocal
from app.models.hydrological_observation import HydrologicalObservation
from app.models.hydrology_collection_state import HydrologyCollectionState

logger = logging.getLogger(__name__)

NWDP_DEFAULT_API_BASE_URL = "https://nwdp.nwic.gov.in/api/3/action"
# Public NWDP CKAN resource IDs verified from official CWC resource metadata.
DEFAULT_RESOURCES = (
    {
        "key": "cwc_krishna_water_level",
        "resource_id": "d80798b9-4b11-4626-8b63-964202ba7216",
        "label": "CWC Krishna Basin River Water Level Telemetry Hourly",
        "measurement": "water_level",
        "value_column": "River Water Level Telemetry Hourly (meter)",
    },
    {
        "key": "cwc_andhra_rainfall",
        "resource_id": "349a10bc-bbe3-40e5-b415-92aa9a797065",
        "label": "CWC Andhra Pradesh Rainfall Telemetry Hourly",
        "measurement": "rainfall",
        "value_column": "Telemetry Hourly Rainfall (mm)",
    },
)


def observation_timezone() -> ZoneInfo:
    zone_name = os.getenv("NWDP_OBSERVATION_TIMEZONE", "Asia/Kolkata").strip() or "Asia/Kolkata"
    try:
        return ZoneInfo(zone_name)
    except ZoneInfoNotFoundError as error:
        raise RuntimeError("NWDP_OBSERVATION_TIMEZONE must be a valid IANA timezone name.") from error


@dataclass(frozen=True)
class CollectionCycleResult:
    started_at: str
    finished_at: str
    sources: list[dict[str, Any]]


def _positive_int_env(name: str, default: int, *, maximum: int | None = None) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as error:
        raise RuntimeError(f"{name} must be a positive integer.") from error
    if value < 1 or (maximum is not None and value > maximum):
        raise RuntimeError(f"{name} must be between 1 and {maximum or 'a positive integer'}.")
    return value


def get_poll_interval_seconds() -> int:
    return _positive_int_env("HYDROLOGY_POLL_INTERVAL_SECONDS", 60, maximum=86400)


def get_stale_after_hours() -> int:
    return _positive_int_env("HYDROLOGY_STALE_AFTER_HOURS", 6, maximum=24 * 365)


def configured_resources() -> list[dict[str, str]]:
    """Use explicit NWDP resource IDs if set, otherwise verified public CWC resources."""
    values = []
    for default in DEFAULT_RESOURCES:
        env_name = "NWDP_" + default["key"].upper() + "_RESOURCE_ID"
        resource_id = os.getenv(env_name, "").strip() or default["resource_id"]
        values.append({**default, "resource_id": resource_id})
    return values


def _source_name(resource: dict[str, str]) -> str:
    return f"nwdp:{resource['key']}"


def _api_url(action: str) -> str:
    base_url = (os.getenv("NWDP_API_BASE_URL", "").strip() or NWDP_DEFAULT_API_BASE_URL).rstrip("/")
    if not base_url.startswith("https://"):
        raise RuntimeError("NWDP_API_BASE_URL must use HTTPS.")
    return f"{base_url}/{action}"


def _parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Data Acquisition Time is missing.")
    text = value.strip()
    parsed: datetime | None = None
    for fmt in ("%d-%m-%Y %H:%M", "%d-%m-%Y %H:%M:%S"):
        try:
            parsed = datetime.strptime(text, fmt).replace(tzinfo=observation_timezone())
            break
        except ValueError:
            continue
    if parsed is None:
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("Data Acquisition Time is not a supported timestamp.") from error
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=observation_timezone())
    return parsed.astimezone(timezone.utc)


def _optional_number(value: Any, field_name: str, *, minimum: float | None = None) -> float | None:
    if value is None or str(value).strip() in {"", "-", "NA", "N/A", "null", "None"}:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} is not numeric.") from error
    if not math.isfinite(number) or (minimum is not None and number < minimum):
        raise ValueError(f"{field_name} is outside the valid range.")
    return number


def _station_key(record: dict[str, Any], latitude: float, longitude: float) -> str:
    # NWDP rows expose station names and geography, not an official station ID.
    stable_parts = (
        str(record.get("Agency", "CWC")).strip().lower(),
        str(record.get("Station", "")).strip().lower(),
        str(record.get("State LGD Code", "")).strip(),
        str(record.get("District LGD Code", "")).strip(),
        f"{latitude:.6f}",
        f"{longitude:.6f}",
    )
    return hashlib.sha256("|".join(stable_parts).encode("utf-8")).hexdigest()[:32]


def normalize_record(record: dict[str, Any], resource: dict[str, str], fetched_at: datetime) -> dict[str, Any]:
    """Normalize one real CKAN row; source fields that are not measured stay null."""
    if not isinstance(record, dict):
        raise ValueError("NWDP record is not an object.")
    record_id = record.get("_id")
    try:
        source_record_id = int(record_id)
    except (TypeError, ValueError) as error:
        raise ValueError("NWDP record is missing a numeric _id.") from error
    station_name = str(record.get("Station", "")).strip()
    if not station_name or station_name == "-":
        raise ValueError("NWDP record is missing station name.")
    latitude = _optional_number(record.get("Latitude"), "Latitude", minimum=-90)
    longitude = _optional_number(record.get("Longitude"), "Longitude", minimum=-180)
    if latitude is None or longitude is None or latitude > 90 or longitude > 180:
        raise ValueError("NWDP record has invalid station coordinates.")
    observation_time = _parse_timestamp(record.get("Data Acquisition Time"))
    measured_value = _optional_number(record.get(resource["value_column"]), resource["measurement"], minimum=0)
    if measured_value is None:
        raise ValueError(f"NWDP record has no measured {resource['measurement']} value.")

    river_value = str(record.get("Local River") or record.get("River") or "").strip()
    if river_value in {"", "-", "None", "null"}:
        river_value = str(record.get("River") or "").strip()
    river_name = river_value if river_value not in {"", "-", "None", "null"} else None
    state_value = str(record.get("State") or "").strip()
    district_value = str(record.get("District") or "").strip()
    source = _source_name(resource)

    return {
        "source": source,
        "source_resource_id": resource["resource_id"],
        "source_record_id": source_record_id,
        "station_id": _station_key(record, latitude, longitude),
        "station_name": station_name,
        "river_name": river_name,
        "state_name": state_value if state_value not in {"", "-"} else None,
        "district_name": district_value if district_value not in {"", "-"} else None,
        "latitude": latitude,
        "longitude": longitude,
        "water_level": measured_value if resource["measurement"] == "water_level" else None,
        # The verified level dataset only exposes Is_DischargeDataAvailable,
        # not a discharge measurement; never treat that flag as a value.
        "discharge": None,
        "rainfall": measured_value if resource["measurement"] == "rainfall" else None,
        "observation_time": observation_time,
        "fetched_at": fetched_at,
    }


def _request_page(resource_id: str, *, offset: int, limit: int) -> dict[str, Any]:
    url = _api_url("datastore_search")
    timeout = _positive_int_env("NWDP_TIMEOUT_SECONDS", 20, maximum=180)
    try:
        response = requests.get(
            url,
            params={
                "resource_id": resource_id,
                "limit": limit,
                "offset": offset,
                "sort": "_id desc",
                "include_total": "true",
            },
            timeout=timeout,
            headers={"Accept": "application/json", "User-Agent": "DisasterGuard-AI/1.0"},
        )
    except requests.Timeout as error:
        logger.warning("NWDP datastore request timed out (resource=%s, offset=%s).", resource_id, offset)
        raise RuntimeError("NWDP request timed out.") from error
    except requests.RequestException as error:
        logger.warning("NWDP datastore request failed (%s).", type(error).__name__)
        raise RuntimeError("NWDP connection failed.") from None

    if response.status_code >= 400:
        logger.warning("NWDP datastore returned HTTP %s for resource %s.", response.status_code, resource_id)
        raise RuntimeError(f"NWDP returned HTTP {response.status_code}.")
    try:
        payload = response.json()
    except ValueError as error:
        raise RuntimeError("NWDP returned malformed JSON.") from error
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise RuntimeError("NWDP datastore response did not report success.")
    result = payload.get("result")
    if not isinstance(result, dict) or not isinstance(result.get("records"), list):
        raise RuntimeError("NWDP datastore response is missing its records list.")
    return result


def _fetch_new_rows(resource: dict[str, str], high_water_id: int | None, page_size: int) -> tuple[list[dict[str, Any]], int, int]:
    """Fetch initial history or only appended records using official CKAN _id ordering."""
    records: list[dict[str, Any]] = []
    offset = 0
    pages = 0
    maximum_pages = _positive_int_env("HYDROLOGY_MAX_PAGES_PER_CYCLE", 64, maximum=1000)
    highest_seen = high_water_id or 0
    finished = False
    while pages < maximum_pages:
        result = _request_page(resource["resource_id"], offset=offset, limit=page_size)
        page_records = result["records"]
        if not page_records:
            finished = True
            break
        pages += 1
        ids: list[int] = []
        for row in page_records:
            if not isinstance(row, dict):
                continue
            try:
                row_id = int(row.get("_id"))
            except (TypeError, ValueError):
                continue
            ids.append(row_id)
            if high_water_id is None or row_id > high_water_id:
                records.append(row)
                highest_seen = max(highest_seen, row_id)
        if high_water_id is not None and ids and min(ids) <= high_water_id:
            finished = True
            break
        offset += len(page_records)
        total = result.get("total")
        if len(page_records) < page_size or (isinstance(total, int) and offset >= total):
            finished = True
            break
    if not finished:
        raise RuntimeError(f"NWDP page limit reached for resource {resource['resource_id']}; cursor was not advanced.")
    return records, highest_seen, pages


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _state_row(db: Session, source: str) -> HydrologyCollectionState:
    state = db.get(HydrologyCollectionState, source)
    if state is None:
        state = HydrologyCollectionState(source=source, status="UNAVAILABLE", message="No collection run yet.")
        db.add(state)
        db.flush()
    return state


def collect_hydrology_cycle() -> dict[str, Any]:
    """Fetch and persist new records from configured public CWC/NWDP resources."""
    resources = configured_resources()
    page_size = _positive_int_env("NWDP_PAGE_SIZE", 1000, maximum=32000)
    cycle_started = datetime.now(timezone.utc)
    logger.info("NWDP hydrology collection started for %d public resources.", len(resources))
    results: list[dict[str, Any]] = []

    for resource in resources:
        source = _source_name(resource)
        fetched_at = datetime.now(timezone.utc)
        result: dict[str, Any] = {
            "source": source,
            "resource_id": resource["resource_id"],
            "received": 0,
            "inserted": 0,
            "duplicates_skipped": 0,
            "parse_errors": 0,
            "error": None,
        }
        db = SessionLocal()
        try:
            state = _state_row(db, source)
            state.source_resource_id = resource["resource_id"]
            state.last_checked_at = cycle_started
            max_inserted_id = db.scalar(
                select(func.max(HydrologicalObservation.source_record_id)).where(
                    HydrologicalObservation.source_resource_id == resource["resource_id"]
                )
            )
            cursors = [value for value in (max_inserted_id, state.source_record_high_watermark) if value is not None]
            high_water_id = max(cursors) if cursors else None
            try:
                logger.info("Requesting NWDP datastore resource %s.", resource["resource_id"])
                raw_records, newest_id, pages = _fetch_new_rows(resource, high_water_id, page_size)
                result["received"] = len(raw_records)
                result["pages_read"] = pages
                existing_pairs = set(
                    db.execute(
                        select(
                            HydrologicalObservation.station_id,
                            HydrologicalObservation.observation_time,
                        ).where(HydrologicalObservation.source_resource_id == resource["resource_id"])
                    ).all()
                )
                seen_pairs = {
                    (station_id, _utc_naive(observation_time))
                    for station_id, observation_time in existing_pairs
                }
                max_observation = _aware_utc(state.last_observation_at) if state.last_observation_at else None
                for raw_record in raw_records:
                    try:
                        normalized = normalize_record(raw_record, resource, fetched_at)
                    except (TypeError, ValueError, OverflowError) as error:
                        result["parse_errors"] += 1
                        logger.warning("Skipped malformed NWDP row for %s (%s).", source, str(error))
                        continue
                    pair = (normalized["station_id"], _utc_naive(normalized["observation_time"]))
                    if pair in seen_pairs:
                        result["duplicates_skipped"] += 1
                        continue
                    seen_pairs.add(pair)
                    stored = {**normalized, "observation_time": _utc_naive(normalized["observation_time"]), "fetched_at": _utc_naive(fetched_at)}
                    db.add(HydrologicalObservation(**stored))
                    result["inserted"] += 1
                    if max_observation is None or normalized["observation_time"] > max_observation:
                        max_observation = normalized["observation_time"]

                state.last_successful_fetch_at = fetched_at.replace(tzinfo=None)
                state.last_observation_at = _utc_naive(max_observation) if max_observation else None
                state.source_record_high_watermark = newest_id
                state.records_received = result["received"]
                state.inserted_count = result["inserted"]
                state.duplicates_skipped = result["duplicates_skipped"]
                state.parse_errors = result["parse_errors"]
                if result["parse_errors"]:
                    state.status = "ERROR"
                    state.message = f"Skipped {result['parse_errors']} malformed source rows; cursor advanced to avoid blocking newer records."
                else:
                    state.status = "READY" if state.last_observation_at else "UNAVAILABLE"
                    state.message = "Public NWDP CWC telemetry collected." if state.last_observation_at else "No valid observations were returned."
                db.commit()
                logger.info(
                    "NWDP collection source=%s received=%d inserted=%d duplicates=%d parse_errors=%d.",
                    source, result["received"], result["inserted"], result["duplicates_skipped"], result["parse_errors"],
                )
            except Exception as error:
                db.rollback()
                state = _state_row(db, source)
                state.last_checked_at = cycle_started
                state.status = "ERROR"
                state.message = str(error)[:500]
                state.records_received = result["received"]
                state.inserted_count = 0
                state.duplicates_skipped = result["duplicates_skipped"]
                state.parse_errors = result["parse_errors"]
                db.commit()
                result["error"] = str(error)
                logger.warning("NWDP collection failed for %s (%s).", source, type(error).__name__)
            results.append(result)
        finally:
            db.close()

    finished = datetime.now(timezone.utc)
    logger.info("NWDP hydrology collection finished in %.2f seconds.", (finished - cycle_started).total_seconds())
    return {"started_at": cycle_started.isoformat(), "finished_at": finished.isoformat(), "sources": results}


async def run_hydrology_collector() -> None:
    """Poll immediately then on a configurable interval; no prediction is triggered."""
    loop = asyncio.get_running_loop()
    interval = get_poll_interval_seconds()
    next_cycle = loop.time()
    while True:
        try:
            await asyncio.to_thread(collect_hydrology_cycle)
        except Exception as error:
            logger.exception("Hydrology collection cycle failed (%s).", type(error).__name__)
        next_cycle += interval
        await asyncio.sleep(max(0.0, next_cycle - loop.time()))


def get_source_states(db: Session) -> list[HydrologyCollectionState]:
    return list(db.scalars(select(HydrologyCollectionState).order_by(HydrologyCollectionState.source)).all())


def get_latest_observations(db: Session, *, station_id: str | None = None, source: str | None = None, limit: int = 100) -> list[HydrologicalObservation]:
    latest_time = (
        select(
            HydrologicalObservation.source.label("source"),
            HydrologicalObservation.station_id.label("station_id"),
            func.max(HydrologicalObservation.observation_time).label("latest_time"),
        )
        .group_by(HydrologicalObservation.source, HydrologicalObservation.station_id)
        .subquery()
    )
    query = (
        select(HydrologicalObservation)
        .join(
            latest_time,
            (HydrologicalObservation.source == latest_time.c.source)
            & (HydrologicalObservation.station_id == latest_time.c.station_id)
            & (HydrologicalObservation.observation_time == latest_time.c.latest_time),
        )
        .order_by(HydrologicalObservation.observation_time.desc())
        .limit(limit)
    )
    if station_id:
        query = query.where(HydrologicalObservation.station_id == station_id)
    if source:
        query = query.where(HydrologicalObservation.source == source)
    return list(db.scalars(query).all())


def get_observations(
    db: Session,
    *,
    station_id: str | None = None,
    source: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    limit: int = 500,
) -> list[HydrologicalObservation]:
    query = select(HydrologicalObservation).order_by(HydrologicalObservation.observation_time.desc()).limit(limit)
    if station_id:
        query = query.where(HydrologicalObservation.station_id == station_id)
    if source:
        query = query.where(HydrologicalObservation.source == source)
    if start_time:
        query = query.where(HydrologicalObservation.observation_time >= _utc_naive(start_time))
    if end_time:
        query = query.where(HydrologicalObservation.observation_time <= _utc_naive(end_time))
    return list(db.scalars(query).all())


def get_stations(db: Session) -> list[dict[str, Any]]:
    latest = get_latest_observations(db, limit=10000)
    stations: dict[str, dict[str, Any]] = {}
    for row in latest:
        station = stations.setdefault(
            row.station_id,
            {
                "station_id": row.station_id,
                "station_name": row.station_name,
                "river_name": row.river_name,
                "state_name": row.state_name,
                "district_name": row.district_name,
                "latitude": row.latitude,
                "longitude": row.longitude,
                "latest_observation_time": row.observation_time,
                "sources": [],
            },
        )
        if row.source not in station["sources"]:
            station["sources"].append(row.source)
        if row.observation_time > station["latest_observation_time"]:
            station["latest_observation_time"] = row.observation_time
    return list(stations.values())
