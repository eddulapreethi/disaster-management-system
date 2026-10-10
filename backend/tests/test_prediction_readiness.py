import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database.connection import Base
from app.models.prediction import Prediction
from app.models.user import User
from app.models.weather_observation import WeatherObservation
from app.schemas.prediction import PredictionCreate
from app.services.data_readiness_service import get_data_readiness
from app.services.prediction_service import create_prediction


class PredictionReadinessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.db = self.session_factory()
        self.user = User(
            name="Readiness test",
            email="readiness@example.test",
            hashed_password="unused",
        )
        self.db.add(self.user)
        self.db.commit()
        self.db.refresh(self.user)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)

    def test_missing_model_and_unverified_schema_keep_ml_statuses_not_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            missing_model = os.path.join(temporary_directory, "missing-model.joblib")
            with (
                patch.dict(os.environ, {"DISASTERGUARD_MODEL_PATH": missing_model}),
                patch(
                    "app.services.data_readiness_service._weather_status",
                    return_value={"status": "READY", "message": "test"},
                ),
                patch(
                    "app.services.data_readiness_service.get_hydrology_status",
                    return_value={"status": "READY", "message": "test", "sources": []},
                ),
            ):
                readiness = get_data_readiness(self.db, self.user)

        self.assertEqual(readiness["ml_model"]["status"], "NOT_READY")
        self.assertIn("No trained model artifact", readiness["ml_model"]["message"])
        self.assertEqual(readiness["features"]["status"], "NOT_READY")
        self.assertIn("authoritative units", readiness["features"]["message"])
        self.assertEqual(readiness["prediction"]["status"], "NOT_READY")
        self.assertIn("not verified", readiness["prediction"]["message"])

    def test_weather_estimate_uses_stored_observation_not_client_supplied_values(self) -> None:
        now = datetime.now(timezone.utc)
        observation = WeatherObservation(
            station_id="test-station",
            station_name="Test station",
            source="open-meteo",
            latitude=9.9312,
            longitude=76.2673,
            temperature_c=30,
            humidity_percent=70,
            precipitation_mm=12,
            rain_mm=10,
            wind_speed_kmh=8,
            pressure_hpa=1008,
            observation_time=now - timedelta(minutes=5),
            fetched_at=now,
        )
        self.db.add(observation)
        self.db.commit()
        self.db.refresh(observation)
        request = PredictionCreate(
            disaster_type="flood",
            latitude=9.9312,
            longitude=76.2673,
            weather_observation_id=observation.id,
            rainfall_mm=0,
            temperature_c=25,
            wind_speed_kmh=0,
        )

        prediction, details = create_prediction(self.db, self.user, request)

        self.assertEqual(prediction.rainfall_mm, 10)
        self.assertEqual(prediction.temperature_c, 30)
        self.assertEqual(prediction.wind_speed_kmh, 8)
        self.assertEqual(details["model_source"], "weather_heuristic")
        self.assertEqual(details["input_provenance"]["source"], "open-meteo")
        self.assertEqual(details["input_provenance"]["station_name"], "Test station")
        self.assertIsNone(details["target_value"])

    def test_flood_estimate_rejects_missing_weather_observation_reference(self) -> None:
        request = PredictionCreate(
            disaster_type="flood",
            latitude=9.9312,
            longitude=76.2673,
            rainfall_mm=10,
            temperature_c=30,
            wind_speed_kmh=8,
        )

        with self.assertRaisesRegex(ValueError, "weather_observation_id is required"):
            create_prediction(self.db, self.user, request)

        self.assertEqual(self.db.scalars(select(Prediction)).all(), [])

    def test_unverified_feature_vectors_are_rejected_instead_of_scored_or_persisted(self) -> None:
        request = PredictionCreate(
            disaster_type="flood",
            latitude=9.9312,
            longitude=76.2673,
            rainfall_mm=10,
            temperature_c=30,
            wind_speed_kmh=8,
            features={"MonsoonIntensity": 4.0},
        )

        with self.assertRaisesRegex(ValueError, "validated feature-source mapping"):
            create_prediction(self.db, self.user, request)

        self.assertEqual(self.db.scalars(select(Prediction)).all(), [])
