from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.api.simulations import simulate
from app.database.connection import Base
from app.models.simulation import Simulation
from app.models.user import User
from app.services.simulation_service import SimulationInput


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def test_simulation_fetches_weather_for_selected_location_and_saves_coordinates(db: Session) -> None:
    user = User(name="Test user", email="simulation@example.test", hashed_password="unused")
    db.add(user)
    db.commit()
    db.refresh(user)
    weather = {
        "precipitation_mm": 0.0,
        "temperature_c": 24.0,
        "wind_speed_kmh": 7.0,
        "source": "open-meteo",
        "observation_time": datetime.now(timezone.utc),
    }

    with patch("app.api.simulations.fetch_location_weather", return_value=weather) as fetch:
        result = simulate(
            SimulationInput(disaster_type="flood", latitude=51.5072, longitude=-0.1276, additional_rainfall_mm=10),
            db,
            user,
        )

    fetch.assert_called_once_with(51.5072, -0.1276)
    assert result["baseline_risk_score"] == 0
    assert result["scenario_risk_score"] == 8
    saved = db.scalars(select(Simulation)).one()
    assert (saved.latitude, saved.longitude) == (51.5072, -0.1276)
    assert saved.results["weather_source"] == "open-meteo"


def test_simulation_source_failure_returns_error_without_saving(db: Session) -> None:
    user = User(name="Test user", email="failed-simulation@example.test", hashed_password="unused")
    db.add(user)
    db.commit()
    request = SimulationInput(disaster_type="flood", latitude=9.9, longitude=76.2)

    with patch(
        "app.api.simulations.fetch_location_weather",
        side_effect=RuntimeError("weather is unavailable"),
    ):
        with pytest.raises(HTTPException) as raised:
            simulate(request, db, user)

    assert raised.value.status_code == 502
    assert "weather is unavailable" in raised.value.detail
    assert db.scalars(select(Simulation)).all() == []
