from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.models.user import User
from app.services.historical_data_readiness import get_historical_analytics
from app.utils.authentication import get_current_user

router = APIRouter(prefix="/historical-data", tags=["historical data"])
PROJECT_ROOT = Path(__file__).resolve().parents[3]


@router.get("/analytics")
def historical_analytics(
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        return get_historical_analytics(PROJECT_ROOT)
    except (OSError, ValueError) as error:
        raise HTTPException(status_code=503, detail=f"Historical analytics are unavailable: {error}") from error
