from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.models.user import User
from app.schemas.alert import AlertCreate, AlertRead
from app.services.alert_service import create_alert, list_alerts
from app.utils.authentication import get_current_user

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("", response_model=list[AlertRead])
def get_alerts(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return list_alerts(db, user)


@router.post("", response_model=AlertRead, status_code=status.HTTP_201_CREATED)
def post_alert(
    data: AlertCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return create_alert(db, user, data)