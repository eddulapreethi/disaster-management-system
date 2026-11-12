import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database.connection import Base
from app.api.predictions import predict as prediction_endpoint
from app.models.prediction import Prediction
from app.models.user import User
from app.schemas.prediction import PredictionCreate
from app.services.data_readiness_service import get_data_readiness
from app.services.prediction_service import PredictionNotReadyError, classify_risk_score, create_prediction


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
        self.assertEqual(readiness["features"]["contract_status"], "VALIDATED")
        self.assertEqual(readiness["features"]["legacy_feature_schema_status"], "RETIRED")
        self.assertIn("No compatible model or live runtime feature builder", readiness["features"]["message"])
        self.assertEqual(readiness["prediction"]["status"], "NOT_READY")
        self.assertIn("not verified", readiness["prediction"]["message"])
        self.assertEqual(readiness["flood_training_data"]["status"], "NOT_READY")
        self.assertEqual(
            readiness["flood_training_data"]["target_id"],
            "cwc_gauge_danger_level_exceedance_24h_v1",
        )
        self.assertEqual(readiness["flood_training_data"]["prediction_horizon_hours"], 24)
        self.assertIn(
            "verified_window_labels",
            readiness["flood_training_data"]["missing_evidence"],
        )
        self.assertIn(
            "gauge_coverage_evidence",
            readiness["flood_training_data"]["missing_evidence"],
        )

    def test_flood_prediction_is_unavailable_even_when_weather_inputs_are_supplied(self) -> None:
        request = PredictionCreate(
            disaster_type="flood",
            latitude=9.9312,
            longitude=76.2673,
            rainfall_mm=0,
            temperature_c=25,
            wind_speed_kmh=0,
        )

        with self.assertRaisesRegex(PredictionNotReadyError, "No score was calculated or saved"):
            create_prediction(self.db, self.user, request)
        self.assertEqual(self.db.scalars(select(Prediction)).all(), [])

    def test_prediction_request_rejects_unsupported_weather_observation_id(self) -> None:
        with self.assertRaises(ValidationError):
            PredictionCreate(
                disaster_type="storm",
                latitude=9.9312,
                longitude=76.2673,
                rainfall_mm=0,
                temperature_c=25,
                wind_speed_kmh=0,
                weather_observation_id=123,
            )

    def test_heuristic_risk_categories_at_existing_threshold_boundaries(self) -> None:
        cases = [
            (29.99, ("low", "low")),
            (30, ("moderate", "medium")),
            (30.01, ("moderate", "medium")),
            (59.99, ("moderate", "medium")),
            (60, ("high", "high")),
            (60.01, ("high", "high")),
            (79.99, ("high", "high")),
            (80, ("critical", "high")),
            (80.01, ("critical", "high")),
        ]

        for score, expected in cases:
            with self.subTest(score=score):
                self.assertEqual(classify_risk_score(score), expected)

    def test_flood_prediction_without_weather_still_reports_model_unavailable(self) -> None:
        request = PredictionCreate(
            disaster_type="flood",
            latitude=9.9312,
            longitude=76.2673,
            rainfall_mm=10,
            temperature_c=30,
            wind_speed_kmh=8,
        )

        with self.assertRaisesRegex(PredictionNotReadyError, "no validated trained model"):
            create_prediction(self.db, self.user, request)

        self.assertEqual(self.db.scalars(select(Prediction)).all(), [])

    def test_prediction_endpoint_returns_service_unavailable_without_saving(self) -> None:
        request = PredictionCreate(
            disaster_type="flood",
            latitude=9.9312,
            longitude=76.2673,
            rainfall_mm=10,
            temperature_c=30,
            wind_speed_kmh=8,
        )

        with self.assertRaises(HTTPException) as raised:
            prediction_endpoint(request, self.db, self.user)

        self.assertEqual(raised.exception.status_code, 503)
        self.assertIn("No score was calculated or saved", raised.exception.detail)
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

    def test_demonstrator_risk_band_matches_the_displayed_risk_level_thresholds(self) -> None:
        request = PredictionCreate(
            disaster_type="storm",
            latitude=9.9,
            longitude=76.2,
            rainfall_mm=0,
            temperature_c=25,
            wind_speed_kmh=37.5,
        )

        prediction, details = create_prediction(self.db, self.user, request)

        self.assertEqual(prediction.risk_score, 30)
        self.assertEqual(prediction.risk_level, "moderate")
        self.assertEqual(details["risk_band"], "medium")
        self.assertIn("unvalidated demonstrator", details["explanation"])
