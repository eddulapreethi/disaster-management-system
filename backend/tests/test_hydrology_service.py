"""Unit tests use synthetic fixture rows only; they are not operational source data."""

import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.database.connection import Base
from app.models.hydrological_observation import HydrologicalObservation
from app.models.hydrology_collection_state import HydrologyCollectionState
from app.schemas.hydrology import HydrologyStatusResponse
from app.services import hydrology_service as service
from app.services.data_readiness_service import get_hydrology_status


WATER_RESOURCE = service.DEFAULT_RESOURCES[0]
RAIN_RESOURCE = service.DEFAULT_RESOURCES[1]


def water_fixture(record_id: int, station: str, timestamp: str, level: str = "351.953") -> dict:
    return {
        "_id": record_id,
        "Station": station,
        "Agency": "CWC",
        "State LGD Code": "29",
        "State": "Karnataka",
        "District LGD Code": "635",
        "District": "Yadgir",
        "River": "Krishna",
        "Local River": "Bhima",
        "Latitude": "16.73750000",
        "Longitude": "77.12527778",
        "Data Acquisition Time": timestamp,
        "River Water Level Telemetry Hourly (meter)": level,
        "Is_DischargeDataAvailable": "Yes",
    }


def rain_fixture(record_id: int, timestamp: str, rainfall: str = "1.5") -> dict:
    return {
        "_id": record_id,
        "Station": "Test Rain Gauge",
        "Agency": "CWC",
        "State LGD Code": "28",
        "State": "Andhra Pradesh",
        "District LGD Code": "748",
        "District": "Eluru",
        "River": "Godavari",
        "Local River": "Godavari",
        "Latitude": "17.24583333",
        "Longitude": "81.65972222",
        "Data Acquisition Time": timestamp,
        "Telemetry Hourly Rainfall (mm)": rainfall,
    }


class HydrologyServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)
        self.session_patch = patch.object(service, "SessionLocal", self.session_factory)
        self.session_patch.start()
        self.addCleanup(self.session_patch.stop)
        self.addCleanup(self.engine.dispose)

    def test_normalizes_cwc_fields_and_india_timestamp_as_utc(self) -> None:
        fetched = datetime(2026, 10, 6, 6, 0, tzinfo=timezone.utc)
        normalized = service.normalize_record(
            water_fixture(5, "Yadgir", "28-09-2026 02:00"), WATER_RESOURCE, fetched
        )
        self.assertEqual(normalized["water_level"], 351.953)
        self.assertIsNone(normalized["discharge"])
        self.assertEqual(normalized["river_name"], "Bhima")
        self.assertEqual(normalized["observation_time"], datetime(2026, 9, 27, 20, 30, tzinfo=timezone.utc))
        self.assertEqual(normalized["fetched_at"], fetched)

    def test_normalizes_rainfall_and_missing_values_are_not_fabricated(self) -> None:
        normalized = service.normalize_record(
            rain_fixture(2, "01-05-2026 14:30", "0.5"), RAIN_RESOURCE,
            datetime(2026, 10, 6, tzinfo=timezone.utc),
        )
        self.assertEqual(normalized["rainfall"], 0.5)
        self.assertIsNone(normalized["water_level"])
        self.assertIsNone(normalized["discharge"])

    def test_rejects_malformed_timestamp_and_coordinates(self) -> None:
        with self.assertRaisesRegex(ValueError, "timestamp"):
            service.normalize_record(water_fixture(1, "Gauge", "not-a-time"), WATER_RESOURCE, datetime.now(timezone.utc))
        invalid = water_fixture(1, "Gauge", "01-10-2026 10:00")
        invalid["Latitude"] = "91"
        with self.assertRaisesRegex(ValueError, "coordinates"):
            service.normalize_record(invalid, WATER_RESOURCE, datetime.now(timezone.utc))

    def test_collection_is_incremental_and_duplicate_station_time_is_skipped(self) -> None:
        water_rows = [
            water_fixture(3, "Yadgir", "28-09-2026 02:00"),
            water_fixture(2, "Yadgir", "28-09-2026 02:00"),
            water_fixture(1, "Other Gauge", "28-09-2026 01:00"),
        ]
        rain_rows = [rain_fixture(1, "01-05-2026 14:30")]

        def request_page(resource_id: str, *, offset: int, limit: int) -> dict:
            rows = water_rows if resource_id == WATER_RESOURCE["resource_id"] else rain_rows
            return {"records": rows[offset:offset + limit], "total": len(rows)}

        with patch.object(service, "_request_page", side_effect=request_page), patch.dict(
            os.environ, {"NWDP_PAGE_SIZE": "10", "NWDP_MAX_PAGES_PER_CYCLE": "10"}
        ):
            first_cycle = service.collect_hydrology_cycle()
            with self.session_factory() as db:
                observations = list(db.scalars(select(HydrologicalObservation)).all())
                water_state = db.get(HydrologyCollectionState, service._source_name(WATER_RESOURCE))
            self.assertEqual(len(observations), 3)
            self.assertEqual(water_state.duplicates_skipped, 1)
            self.assertEqual(water_state.source_record_high_watermark, 3)
            self.assertEqual(first_cycle["sources"][0]["inserted"], 2)

            # Second cycle sees only records at/below the persisted high-water mark.
            second_cycle = service.collect_hydrology_cycle()
            with self.session_factory() as db:
                observations_after = list(db.scalars(select(HydrologicalObservation)).all())
            self.assertEqual(len(observations_after), 3)
            self.assertEqual(second_cycle["sources"][0]["received"], 0)

    def test_provider_failure_is_recorded_without_crashing_cycle(self) -> None:
        with patch.object(service, "configured_resources", return_value=[WATER_RESOURCE]), patch.object(
            service, "_request_page", side_effect=RuntimeError("provider unavailable")
        ):
            result = service.collect_hydrology_cycle()
        self.assertEqual(result["sources"][0]["error"], "provider unavailable")
        with self.session_factory() as db:
            state = db.get(HydrologyCollectionState, service._source_name(WATER_RESOURCE))
            self.assertEqual(state.status, "ERROR")
            self.assertIsNone(db.scalar(select(HydrologicalObservation.id)))

    def test_no_observations_report_unavailable_readiness(self) -> None:
        with self.session_factory() as db:
            status = get_hydrology_status(db)
        self.assertEqual(status["status"], "UNAVAILABLE")
        self.assertTrue(all(source["status"] == "UNAVAILABLE" for source in status["sources"]))
        response = HydrologyStatusResponse.model_validate(status)
        self.assertTrue(response.message)

    def test_malformed_row_does_not_block_newer_records(self) -> None:
        malformed = water_fixture(1, "Old Gauge", "not-a-time")
        records = [water_fixture(2, "Yadgir", "28-09-2026 02:00"), malformed]

        with patch.object(service, "configured_resources", return_value=[WATER_RESOURCE]), patch.object(
            service, "_request_page", return_value={"records": records, "total": len(records)}
        ), patch.dict(os.environ, {"NWDP_PAGE_SIZE": "10"}):
            result = service.collect_hydrology_cycle()
        self.assertEqual(result["sources"][0]["parse_errors"], 1)
        with self.session_factory() as db:
            state = db.get(HydrologyCollectionState, service._source_name(WATER_RESOURCE))
            self.assertEqual(state.source_record_high_watermark, 2)
            self.assertEqual(state.status, "ERROR")
            self.assertEqual(db.scalar(select(func.count(HydrologicalObservation.id))), 1)

    def test_old_source_observations_report_stale_readiness(self) -> None:
        old_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
        with self.session_factory() as db:
            for resource, fixture in (
                (WATER_RESOURCE, water_fixture(1, "Yadgir", "01-01-2026 05:00")),
                (RAIN_RESOURCE, rain_fixture(1, "01-01-2026 05:00")),
            ):
                normalized = service.normalize_record(fixture, resource, old_time)
                normalized["observation_time"] = normalized["observation_time"].replace(tzinfo=None)
                normalized["fetched_at"] = old_time.replace(tzinfo=None)
                db.add(HydrologicalObservation(**normalized))
                db.add(HydrologyCollectionState(
                    source=service._source_name(resource),
                    source_resource_id=resource["resource_id"],
                    status="READY",
                    last_successful_fetch_at=old_time.replace(tzinfo=None),
                    last_observation_at=old_time.replace(tzinfo=None),
                ))
            db.commit()
            status = get_hydrology_status(db)
        self.assertEqual(status["status"], "STALE")
        self.assertTrue(all(source["status"] == "STALE" for source in status["sources"]))
        self.assertEqual(status["sources"][0]["latest_station"], "Yadgir")


if __name__ == "__main__":
    unittest.main()
