from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.models.prediction import Prediction
from app.models.user import User
from app.utils.authentication import get_current_user

router = APIRouter(prefix="/gis", tags=["GIS"])


@router.get("/risk-points")
def risk_points(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    records = db.scalars(
        select(Prediction)
        .where(Prediction.user_id == user.id)
        .order_by(Prediction.created_at.desc())
    ).all()

    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [item.longitude, item.latitude],
                },
                "properties": {
                    "prediction_id": item.id,
                    "disaster_type": item.disaster_type,
                    "risk_score": item.risk_score,
                    "risk_level": item.risk_level,
                    "created_at": item.created_at.isoformat(),
                },
            }
            for item in records
        ],
    }