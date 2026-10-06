import os
import asyncio
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from unittest.mock import AsyncMock

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database.connection import Base
from app.database.database import _upgrade_sqlite_weather_schema
from app.models.weather_observation import WeatherObservation
from app.services import weather_service as service


class WeatherServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)
        self.session_patch = patch.object(service, "SessionLocal", self.session_factory)
        self.session_patch.start()
        self.addCleanup(self.session_patch.stop)
        self.addCleanup(self.engine.dispose)

    def test_collect_weather_cycle_skips_duplicate_station_observation_and_persists_source(self) -> None:
        timestamp = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)
        duplicate = {
            "station_id": "kochi",
            "station_name": "Kochi",
            "latitude": 9.9312,
            "longitude": 76.2673,
            "temperature_c": 30.0,
            "humidity_percent": 70.0,
            "precipitation_mm": 2.5,
            "rain_mm": 2.5,
            "wind_speed_kmh": 12.5,
            "pressure_hpa": 1008.2,
            "observation_time": timestamp,
            "fetched_at": timestamp,
            "source": "open-meteo",
        }

        with patch.object(service, "configured_locations", return_value=[{"name": "Kochi", "latitude": 9.9312, "longitude": 76.2673}]), patch.object(service, "_fetch_batch", return_value=[duplicate, duplicate]):
            first_result = service.collect_weather_cycle()
            second_result = service.collect_weather_cycle()

        with self.session_factory() as db:
            rows = list(db.scalars(select(WeatherObservation)).all())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].source, "open-meteo")
        self.assertIsNotNone(rows[0].created_at)
        self.assertEqual(first_result["stored_observations"], 1)
        self.assertEqual(first_result["duplicates_skipped"], 1)
        self.assertEqual(second_result["stored_observations"], 0)
        self.assertEqual(second_result["duplicates_skipped"], 2)
        self.assertEqual(service.get_latest_observations()[0].source, "open-meteo")

    def test_parse_location_response_normalizes_open_meteo_fields_and_timestamps(self) -> None:
        payload = {
            "current": {
                "time": "2026-10-06T12:00",
                "temperature_2m": 28.5,
                "relative_humidity_2m": 75,
                "precipitation": 1.2,
                "rain": 1.2,
                "wind_speed_10m": 10,
                "surface_pressure": 1008,
            }
        }

        record = service._parse_location_response(
            {"name": "Kochi", "latitude": 9.9312, "longitude": 76.2673}, payload
        )

        self.assertEqual(record["temperature_c"], 28.5)
        self.assertEqual(record["source"], "open-meteo")
        self.assertEqual(record["observation_time"].tzinfo, timezone.utc)
        self.assertNotEqual(record["observation_time"], record["fetched_at"])

    def test_parse_location_response_rejects_missing_requested_fields(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "missing requested fields"):
            service._parse_location_response(
                {"name": "Kochi", "latitude": 9.9312, "longitude": 76.2673},
                {"current": {"time": "2026-10-06T12:00", "temperature_2m": 28}},
            )

    def test_configured_locations_uses_environment_coordinates(self) -> None:
        with patch.dict(
            os.environ,
            {
                "WEATHER_LOCATIONS_JSON": "",
                "WEATHER_LOCATION_NAME": "Test Site",
                "WEATHER_LATITUDE": "12.5",
                "WEATHER_LONGITUDE": "77.6",
            },
        ):
            self.assertEqual(
                service.configured_locations(),
                [{"name": "Test Site", "latitude": 12.5, "longitude": 77.6}],
            )

    def test_poll_interval_is_configurable_and_validated(self) -> None:
        with patch.dict(os.environ, {"WEATHER_POLL_INTERVAL_SECONDS": "45"}):
            self.assertEqual(service.get_poll_interval_seconds(), 45)
        with patch.dict(os.environ, {"WEATHER_POLL_INTERVAL_SECONDS": "0"}):
            with self.assertRaisesRegex(RuntimeError, "positive integer"):
                service.get_poll_interval_seconds()

    def test_failed_source_fetch_sets_error_without_database_insert(self) -> None:
        with patch.object(service, "configured_locations", return_value=[{"name": "Kochi", "latitude": 9.9, "longitude": 76.2}]), patch.object(
            service, "_fetch_batch", side_effect=RuntimeError("network unavailable")
        ):
            result = service.collect_weather_cycle()

        with self.session_factory() as db:
            rows = list(db.scalars(select(WeatherObservation)).all())
        self.assertEqual(rows, [])
        self.assertTrue(result["failed_locations"])
        self.assertEqual(result["stored_observations"], 0)

    def test_weather_status_uses_stored_observation_freshness(self) -> None:
        observation = WeatherObservation(
            station_id="kochi",
            station_name="Kochi",
            source="open-meteo",
            latitude=9.9312,
            longitude=76.2673,
            observation_time=datetime.now(timezone.utc) - timedelta(hours=3),
            fetched_at=datetime.now(timezone.utc),
        )
        with patch.object(service, "get_latest_observations", return_value=[observation]), patch.object(
            service, "get_collector_status", return_value={"failed_locations": [], "last_cycle_finished_at": "checked"}
        ), patch.dict(os.environ, {"WEATHER_MAX_AGE_SECONDS": "7200"}):
            status = service.get_weather_status()

        self.assertEqual(status["status"], "STALE")
        self.assertEqual(status["last_checked"], "checked")
        self.assertIsNotNone(status["last_observation"])

    def test_weather_status_ready_requires_recent_stored_observation(self) -> None:
        observation = WeatherObservation(
            station_id="kochi",
            station_name="Kochi",
            source="open-meteo",
            latitude=9.9312,
            longitude=76.2673,
            observation_time=datetime.now(timezone.utc),
            fetched_at=datetime.now(timezone.utc),
        )
        with patch.object(service, "get_latest_observations", return_value=[observation]), patch.object(
            service, "get_collector_status", return_value={"failed_locations": []}
        ):
            self.assertEqual(service.get_weather_status()["status"], "READY")

    def test_weather_status_distinguishes_unavailable_from_error(self) -> None:
        with patch.object(service, "get_latest_observations", return_value=[]), patch.object(
            service, "get_collector_status", return_value={"failed_locations": []}
        ):
            self.assertEqual(service.get_weather_status()["status"], "UNAVAILABLE")

        with patch.object(service, "get_latest_observations", return_value=[]), patch.object(
            service, "get_collector_status", return_value={"failed_locations": [{"location": "collector"}]}
        ):
            self.assertEqual(service.get_weather_status()["status"], "ERROR")

    def test_sqlite_upgrade_preserves_legacy_duplicates_without_unique_index(self) -> None:
        legacy_engine = create_engine("sqlite:///:memory:")
        try:
            with legacy_engine.begin() as connection:
                connection.exec_driver_sql(
                    "CREATE TABLE weather_observations ("
                    "id INTEGER PRIMARY KEY, station_id VARCHAR(100), station_name VARCHAR(160), "
                    "latitude FLOAT, longitude FLOAT, temperature_c FLOAT, humidity_percent FLOAT, "
                    "precipitation_mm FLOAT, rain_mm FLOAT, wind_speed_kmh FLOAT, pressure_hpa FLOAT, "
                    "observation_time DATETIME, fetched_at DATETIME)"
                )
                connection.exec_driver_sql(
                    "INSERT INTO weather_observations (station_id, station_name, latitude, longitude, observation_time, fetched_at) "
                    "VALUES ('kochi', 'Kochi', 9.9, 76.2, '2026-10-06 12:00:00', '2026-10-06 12:01:00'), "
                    "('kochi', 'Kochi', 9.9, 76.2, '2026-10-06 12:00:00', '2026-10-06 12:02:00')"
                )

            _upgrade_sqlite_weather_schema(legacy_engine)

            with legacy_engine.connect() as connection:
                self.assertEqual(connection.exec_driver_sql("SELECT COUNT(*) FROM weather_observations").scalar_one(), 2)
                self.assertEqual(
                    connection.exec_driver_sql("SELECT COUNT(*) FROM weather_observations WHERE source = 'open-meteo' AND created_at IS NOT NULL").scalar_one(),
                    2,
                )
                unique_indexes = [index for index in connection.exec_driver_sql("PRAGMA index_list('weather_observations')") if index[2]]
                self.assertEqual(unique_indexes, [])
        finally:
            legacy_engine.dispose()

    def test_collector_recovers_from_cycle_failure_and_cancels_cleanly(self) -> None:
        with patch.object(service.asyncio, "to_thread", new=AsyncMock(side_effect=RuntimeError("temporary source failure"))), patch.object(
            service.asyncio, "sleep", new=AsyncMock(side_effect=asyncio.CancelledError)
        ), patch.object(service, "get_poll_interval_seconds", return_value=1):
            with self.assertRaises(asyncio.CancelledError):
                asyncio.run(service.run_weather_collector())

        status = service.get_collector_status()
        self.assertFalse(status["enabled"])
        self.assertEqual(status["failed_locations"][0]["location"], "collector")


if __name__ == "__main__":
    unittest.main()
