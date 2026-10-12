"""Unit tests use synthetic fixture rows only; they are not operational source data."""

import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.database.connection import Base
from app.models.hydrological_observation import HydrologicalObservation
from app.models.hydrology_collection_state import HydrologyCollectionState
from app.schemas.hydrology import HydrologyStatusResponse
from app.api.hydrology import HydrologicalObservationRead as HydrologyApiObservationRead
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

    def test_hydrology_api_exposes_utc_timestamps_and_measurement_units(self) -> None:
        normalized = service.normalize_record(
            water_fixture(5, "Yadgir", "28-09-2026 02:00"),
            WATER_RESOURCE,
            datetime(2026, 10, 6, 6, 0, tzinfo=timezone.utc),
        )
        response = HydrologyApiObservationRead.model_validate(normalized)
        serialized = response.model_dump(mode="json")
        self.assertEqual(serialized["observation_time"], "2026-09-27T20:30:00Z")
        self.assertEqual(serialized["measurement_units"], {"water_level": "m", "rainfall": "mm"})

    def test_rejects_malformed_timestamp_and_coordinates(self) -> None:
        with self.assertRaisesRegex(ValueError, "timestamp"):
            service.normalize_record(water_fixture(1, "Gauge", "not-a-time"), WATER_RESOURCE, datetime.now(timezone.utc))
        invalid = water_fixture(1, "Gauge", "01-10-2026 10:00")
        invalid["Latitude"] = "91"
        with self.assertRaisesRegex(ValueError, "coordinates"):
            service.normalize_record(invalid, WATER_RESOURCE, datetime.now(timezone.utc))

    def test_rejects_malformed_measurement(self) -> None:
        invalid = water_fixture(1, "Gauge", "01-10-2026 10:00", "-143")
        with self.assertRaisesRegex(ValueError, "valid range"):
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
            self.assertEqual(water_state.records_returned, 3)
            self.assertEqual(water_state.valid_records, 3)
            self.assertTrue(water_state.newer_observation_found)
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
            self.assertIn("provider unavailable", state.last_error)
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
        self.assertEqual(status["sources"][0]["freshness_status"], "STALE")
        self.assertEqual(status["sources"][0]["collection_status"], "SUCCESS_EMPTY_RESPONSE")
        self.assertGreater(status["sources"][0]["observation_age_seconds"], 0)
        self.assertEqual(status["sources"][0]["update_frequency"], "Hourly telemetry; publication delays are source-controlled.")
        self.assertEqual(status["sources"][0]["latest_station"], "Yadgir")

    def test_future_source_observation_is_an_error_not_ready(self) -> None:
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        with self.session_factory() as db:
            for resource, fixture in (
                (WATER_RESOURCE, water_fixture(1, "Yadgir", "01-01-2026 05:00")),
                (RAIN_RESOURCE, rain_fixture(1, "01-01-2026 05:00")),
            ):
                normalized = service.normalize_record(fixture, resource, datetime.now(timezone.utc))
                normalized["observation_time"] = future.replace(tzinfo=None)
                db.add(HydrologicalObservation(**normalized))
                db.add(HydrologyCollectionState(
                    source=service._source_name(resource),
                    source_resource_id=resource["resource_id"],
                    status="READY",
                    last_successful_fetch_at=datetime.now(timezone.utc).replace(tzinfo=None),
                    last_observation_at=future.replace(tzinfo=None),
                ))
            db.commit()
            status = get_hydrology_status(db)
        self.assertEqual(status["status"], "ERROR")
        self.assertTrue(all(source["status"] == "ERROR" for source in status["sources"]))
        self.assertTrue(all("future" in source["message"] for source in status["sources"]))

    def test_hydrology_schedule_defaults_to_five_minutes_and_is_configurable(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(service.get_poll_interval_seconds(), 300)
        with patch.dict(os.environ, {"HYDROLOGY_POLL_INTERVAL_SECONDS": "45"}):
            self.assertEqual(service.get_poll_interval_seconds(), 45)

    def test_source_specific_freshness_threshold_overrides_global(self) -> None:
        resource = {
            **WATER_RESOURCE,
            "key": "cwc_krishna_water_level",
        }
        with patch.dict(
            os.environ,
            {
                "HYDROLOGY_STALE_AFTER_HOURS": "6",
                "HYDROLOGY_CWC_KRISHNA_WATER_LEVEL_STALE_AFTER_HOURS": "12",
            },
        ):
            self.assertEqual(service.get_stale_after_hours(resource), 12)

    def test_provider_rows_returned_are_counted_separately_from_newer_rows(self) -> None:
        observations = [
            water_fixture(1, "Yadgir", "28-09-2026 02:00"),
            water_fixture(2, "Yadgir", "28-09-2026 02:00"),
        ]
        with patch.object(service, "configured_resources", return_value=[WATER_RESOURCE]), patch.object(
            service, "_request_page", return_value={"records": observations, "total": 2}
        ), patch.dict(os.environ, {"NWDP_PAGE_SIZE": "10"}):
            result = service.collect_hydrology_cycle()
        self.assertEqual(result["sources"][0]["records_returned"], 2)
        self.assertEqual(result["sources"][0]["valid_records"], 2)
        self.assertEqual(result["sources"][0]["inserted"], 1)
        self.assertEqual(result["sources"][0]["duplicates_skipped"], 1)

    def test_fetch_new_rows_pages_descending_ids_until_saved_cursor(self) -> None:
        pages = [
            {"records": [{"_id": 9}, {"_id": 8}], "total": 8},
            {"records": [{"_id": 7}, {"_id": 6}], "total": 8},
            {"records": [{"_id": 5}, {"_id": 4}], "total": 8},
        ]
        offsets = []

        def request_page(resource_id: str, *, offset: int, limit: int) -> dict:
            offsets.append(offset)
            return pages[len(offsets) - 1]

        with patch.object(service, "_request_page", side_effect=request_page), patch.dict(
            os.environ, {"HYDROLOGY_MAX_PAGES_PER_CYCLE": "10"}
        ):
            records, newest_id, page_count, returned_count, latest_observation = service._fetch_new_rows(
                WATER_RESOURCE,
                high_water_id=5,
                page_size=2,
            )

        self.assertEqual([record["_id"] for record in records], [9, 8, 7, 6])
        self.assertEqual(newest_id, 9)
        self.assertEqual(page_count, 3)
        self.assertEqual(returned_count, 6)
        self.assertEqual(offsets, [0, 2, 4])
        self.assertIsNone(latest_observation)

    def test_fetch_uses_numeric_ids_in_both_orders_and_deduplicates_across_pages(self) -> None:
        descending_pages = [
            {"records": [water_fixture("10", "Gauge", "01-10-2026 10:00"),
                         water_fixture("9", "Gauge", "01-10-2026 09:00")], "total": 4},
            {"records": [water_fixture("9", "Gauge", "01-10-2026 09:00"),
                         water_fixture("8", "Gauge", "01-10-2026 08:00")], "total": 4},
        ]
        with patch.object(
            service, "_request_page", side_effect=descending_pages
        ), patch.dict(os.environ, {"HYDROLOGY_MAX_PAGES_PER_CYCLE": "10"}):
            records, newest_id, pages, returned, latest = service._fetch_new_rows(
                WATER_RESOURCE, high_water_id=8, page_size=2
            )
        self.assertEqual([int(record["_id"]) for record in records], [10, 9])
        self.assertEqual(newest_id, 10)
        self.assertEqual((pages, returned), (2, 4))
        self.assertEqual(latest, service._parse_timestamp("01-10-2026 10:00"))

        for ordered_rows in (
            [water_fixture(8, "Gauge", "01-10-2026 08:00"),
             water_fixture(9, "Gauge", "01-10-2026 09:00"),
             water_fixture(10, "Gauge", "01-10-2026 10:00")],
            [water_fixture(10, "Gauge", "01-10-2026 10:00"),
             water_fixture(9, "Gauge", "01-10-2026 09:00"),
             water_fixture(8, "Gauge", "01-10-2026 08:00")],
        ):
            with patch.object(
                service, "_request_page", return_value={"records": ordered_rows, "total": 3}
            ):
                records, newest_id, _, _, _ = service._fetch_new_rows(
                    WATER_RESOURCE, high_water_id=8, page_size=10
                )
            self.assertEqual([int(record["_id"]) for record in records], [9, 10] if int(ordered_rows[0]["_id"]) == 8 else [10, 9])
            self.assertEqual(newest_id, 10)

    def test_no_new_ids_preserve_cursor_and_report_stale_source(self) -> None:
        old_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
        row = water_fixture(1, "Gauge", "01-01-2026 05:00")
        with self.session_factory() as db:
            normalized = service.normalize_record(row, WATER_RESOURCE, old_time)
            normalized["observation_time"] = normalized["observation_time"].replace(tzinfo=None)
            normalized["fetched_at"] = old_time.replace(tzinfo=None)
            db.add(HydrologicalObservation(**normalized))
            db.add(HydrologyCollectionState(
                source=service._source_name(WATER_RESOURCE),
                source_resource_id=WATER_RESOURCE["resource_id"],
                status="READY",
                source_record_high_watermark=1,
                last_successful_fetch_at=old_time.replace(tzinfo=None),
                last_observation_at=normalized["observation_time"],
            ))
            db.commit()

        with patch.object(service, "configured_resources", return_value=[WATER_RESOURCE]), patch.object(
            service, "_request_page", return_value={"records": [row], "total": 1}
        ), patch.dict(os.environ, {"NWDP_PAGE_SIZE": "10"}):
            result = service.collect_hydrology_cycle()["sources"][0]
            with self.session_factory() as db:
                state = db.get(HydrologyCollectionState, service._source_name(WATER_RESOURCE))
                status = get_hydrology_status(db)["sources"][0]

        self.assertEqual(result["received"], 0)
        self.assertEqual(result["cursor_before"], 1)
        self.assertEqual(result["cursor_after"], 1)
        self.assertEqual(result["latest_source_observation_scanned"], "2025-12-31T23:30:00+00:00")
        self.assertEqual(state.source_record_high_watermark, 1)
        self.assertEqual(status["collection_status"], "SUCCESS_NO_NEW_DATA")
        self.assertEqual(status["freshness_status"], "STALE")

    def test_failed_persistence_does_not_advance_cursor(self) -> None:
        with self.session_factory() as db:
            db.add(HydrologyCollectionState(
                source=service._source_name(WATER_RESOURCE),
                source_resource_id=WATER_RESOURCE["resource_id"],
                status="READY",
                source_record_high_watermark=1,
            ))
            db.commit()

        original_commit = Session.commit
        attempts = 0

        def fail_first_commit(db: Session) -> None:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("simulated persistence failure")
            original_commit(db)

        rows = [water_fixture(2, "Gauge", "01-10-2026 10:00"),
                water_fixture(1, "Gauge", "01-10-2026 09:00")]
        with patch.object(service, "configured_resources", return_value=[WATER_RESOURCE]), patch.object(
            service, "_request_page", return_value={"records": rows, "total": 2}
        ), patch.object(Session, "commit", fail_first_commit):
            result = service.collect_hydrology_cycle()["sources"][0]

        with self.session_factory() as db:
            state = db.get(HydrologyCollectionState, service._source_name(WATER_RESOURCE))
            count = db.scalar(select(func.count(HydrologicalObservation.id)))
        self.assertEqual(result["error"], "simulated persistence failure")
        self.assertEqual(state.source_record_high_watermark, 1)
        self.assertEqual(count, 0)

    def test_successful_fetch_with_no_new_records_is_distinct_from_freshness(self) -> None:
        observation_time = datetime.now(timezone.utc) - timedelta(days=2)
        with self.session_factory() as db:
            normalized = service.normalize_record(
                water_fixture(1, "Yadgir", "01-01-2026 05:00"),
                WATER_RESOURCE,
                observation_time,
            )
            normalized["observation_time"] = observation_time.replace(tzinfo=None)
            normalized["fetched_at"] = observation_time.replace(tzinfo=None)
            db.add(HydrologicalObservation(**normalized))
            db.add(HydrologyCollectionState(
                source=service._source_name(WATER_RESOURCE),
                source_resource_id=WATER_RESOURCE["resource_id"],
                status="READY",
                last_successful_fetch_at=datetime.now(timezone.utc).replace(tzinfo=None),
                records_returned=0,
                last_observation_at=observation_time.replace(tzinfo=None),
            ))
            db.commit()
            status = get_hydrology_status(db)
        water_status = status["sources"][0]
        self.assertEqual(water_status["collection_status"], "SUCCESS_EMPTY_RESPONSE")
        self.assertEqual(water_status["freshness_status"], "STALE")

    def test_collection_status_distinguishes_new_data_from_stale_observation(self) -> None:
        rows = [
            water_fixture(2, "Yadgir", "01-01-2026 05:00"),
            water_fixture(1, "Yadgir", "01-01-2026 04:00"),
        ]
        with patch.object(service, "configured_resources", return_value=[WATER_RESOURCE]), patch.object(
            service, "_request_page", return_value={"records": rows, "total": len(rows)}
        ), patch.dict(os.environ, {"NWDP_PAGE_SIZE": "10"}):
            service.collect_hydrology_cycle()
            with self.session_factory() as db:
                status = get_hydrology_status(db)

        self.assertEqual(status["sources"][0]["collection_status"], "SUCCESS_WITH_NEW_DATA")
        self.assertEqual(status["sources"][0]["freshness_status"], "STALE")

    def test_status_api_schema_includes_diagnostics(self) -> None:
        with self.session_factory() as db:
            response = HydrologyStatusResponse.model_validate(get_hydrology_status(db))
        self.assertEqual(response.poll_interval_seconds, 300)
        self.assertEqual(response.sources[0].collection_status, "UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
