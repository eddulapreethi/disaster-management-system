from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.models.user import User
from app.schemas.alert import AlertCreate


def create_alert(db: Session, user: User, data: AlertCreate) -> Alert:
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