from datetime import datetime, timedelta, timezone
import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.models.user import User
from app.schemas.alert import AlertCreate


def create_alert(db: Session, user: User, data: AlertCreate) -> Alert | None:
    try:
        cooldown_seconds = int(os.getenv("ALERT_DEDUPLICATION_SECONDS", "1800"))
    except ValueError as error:
        raise RuntimeError("ALERT_DEDUPLICATION_SECONDS must be a positive integer.") from error
    if cooldown_seconds < 1:
        raise RuntimeError("ALERT_DEDUPLICATION_SECONDS must be a positive integer.")

    duplicate_query = select(Alert.id).where(
        Alert.user_id == user.id,
        Alert.disaster_type == data.disaster_type,
        Alert.severity == data.severity,
        Alert.latitude == data.latitude if data.latitude is not None else Alert.latitude.is_(None),
        Alert.longitude == data.longitude if data.longitude is not None else Alert.longitude.is_(None),
        Alert.created_at >= datetime.now(timezone.utc) - timedelta(seconds=cooldown_seconds),
    )
    if db.scalar(duplicate_query) is not None:
        return None

    alert = Alert(user_id=user.id, **data.model_dump())
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


def list_alerts(db: Session, user: User) -> list[Alert]:
    return list(
        db.scalars(
            select(Alert).where(Alert.user_id == user.id).order_by(Alert.created_at.desc())
        ).all()
    )