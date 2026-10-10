from datetime import datetime, timezone
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.connection import Base
from app.models.user import User
from app.models.weather_observation import WeatherObservation
from app.services.assistant_service import answer_question


class AssistantServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)
        self.db = self.session_factory()
        self.user = User(name="Test user", email="assistant@example.test", hashed_password="unused")
        self.db.add(self.user)
        self.db.commit()
        self.db.refresh(self.user)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)

    def test_answers_general_disaster_question_with_safety_disclaimer(self) -> None:
        response = answer_question("What is a flood?", self.db, self.user)

        self.assertEqual(response["category"], "general_knowledge")
        self.assertIn("overflow of water", response["answer"])
        self.assertIn("official local emergency services", response["disclaimer"])

    def test_live_weather_reports_unavailable_instead_of_inventing_values(self) -> None:
        response = answer_question("What is the latest weather?", self.db, self.user)

        self.assertEqual(response["category"], "live_system_data")
        self.assertIn("No weather observation is currently stored", response["answer"])

    def test_live_weather_uses_only_a_stored_observation(self) -> None:
        observed_at = datetime(2026, 10, 7, 8, 0, tzinfo=timezone.utc)
        self.db.add(WeatherObservation(
            station_id="kochi",
            station_name="Kochi",
            source="open-meteo",
            latitude=9.9312,
            longitude=76.2673,
            temperature_c=29.5,
            humidity_percent=70,
            precipitation_mm=1.2,
            rain_mm=1.0,
            wind_speed_kmh=10,
            pressure_hpa=1008,
            observation_time=observed_at,
            fetched_at=observed_at,
        ))
        self.db.commit()

        response = answer_question("Tell me the latest weather.", self.db, self.user)

        self.assertIn("Kochi", response["answer"])
        self.assertIn("temperature 29.5 °C", response["answer"])
        self.assertIn("not a forecast", response["answer"])
