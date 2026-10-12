from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.models.user import User
from app.schemas.alert import AlertRead
from app.services.alert_service import list_alerts
from app.utils.authentication import get_current_user

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("", response_model=list[AlertRead])
def get_alerts(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return list_alerts(db, user)
