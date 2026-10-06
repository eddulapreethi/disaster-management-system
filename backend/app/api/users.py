from fastapi import APIRouter, Depends

from app.models.user import User
from app.schemas.user import UserRead
from app.utils.authentication import get_current_user

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserRead)
def read_current_user(user: User = Depends(get_current_user)):
    return user