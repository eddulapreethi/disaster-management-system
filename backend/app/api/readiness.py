from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.models.user import User
from app.services.data_readiness_service import get_data_readiness
from app.utils.authentication import get_current_user

router = APIRouter(prefix="/data-readiness", tags=["data readiness"])


@router.get("")
def data_readiness(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return get_data_readiness(db, user)
