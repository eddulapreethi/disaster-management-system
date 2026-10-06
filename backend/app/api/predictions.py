import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.models.prediction import Prediction
from app.models.user import User
from app.schemas.alert import AlertCreate
from app.schemas.prediction import PredictionCreate, PredictionRead, PredictionResult
from app.services.alert_service import create_alert
from app.services.prediction_service import create_prediction, get_recommendations
from app.utils.authentication import get_current_user

router = APIRouter(prefix="/predictions", tags=["predictions"])


@router.post("", response_model=PredictionResult)
def predict(
    data: PredictionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        prediction, details = create_prediction(db, user, data)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    project_root = str(Path(__file__).resolve().parents[3])
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    from alerts.alert_generator import generate_alert

    alert, _decision = generate_alert(
        {
            "disaster_type": prediction.disaster_type,
            "risk_score": prediction.risk_score,
            "latitude": prediction.latitude,
            "longitude": prediction.longitude,
        }
    )
    if alert is not None:
        create_alert(db, user, AlertCreate(**alert.to_backend_payload()))
    return {
        "prediction": prediction,
        "recommendations": get_recommendations(data.disaster_type, prediction.risk_level),
        "alert_generated": alert is not None,
        **details,
    }


@router.get("", response_model=list[PredictionRead])
def prediction_history(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return list(
        db.scalars(
            select(Prediction)
            .where(Prediction.user_id == user.id)
            .order_by(Prediction.created_at.desc())
        ).all()
    )