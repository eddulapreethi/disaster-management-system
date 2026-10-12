import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from alerts.alert_rules import get_minimum_alert_score
from app.database.connection import Base
from app.models.alert import Alert
from app.models.user import User
from app.schemas.alert import AlertCreate, AlertRead
from app.services.alert_service import create_alert, list_alerts


def test_configured_alert_threshold_is_validated(monkeypatch) -> None:
    monkeypatch.setenv("ALERT_MINIMUM_SCORE", "55.5")
    assert get_minimum_alert_score() == 55.5

    monkeypatch.setenv("ALERT_MINIMUM_SCORE", "nan")
    with pytest.raises(RuntimeError, match="between 0 and 100"):
        get_minimum_alert_score()


def test_alert_lifecycle_persists_once_and_suppresses_same_event_duplicates(monkeypatch) -> None:
    monkeypatch.setenv("ALERT_DEDUPLICATION_SECONDS", "1800")
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            user = User(name="Alert test", email="alerts@example.test", hashed_password="unused")
            db.add(user)
            db.commit()
            db.refresh(user)
            data = AlertCreate(
                title="Moderate storm risk alert",
                message="Automated estimate; not an official warning.",
                severity="moderate",
                disaster_type="storm",
                latitude=9.9,
                longitude=76.2,
            )

            first = create_alert(db, user, data)
            duplicate = create_alert(db, user, data)

            assert first is not None
            assert duplicate is None
            assert first.created_at is not None
            assert AlertRead.model_validate(first).model_dump(mode="json")["created_at"].endswith("Z")
            assert [alert.id for alert in list_alerts(db, user)] == [first.id]
            assert len(db.scalars(select(Alert)).all()) == 1
    finally:
        engine.dispose()
