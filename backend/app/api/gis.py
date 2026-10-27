from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.models.prediction import Prediction
from app.models.user import User
from app.services.gis_readiness_service import GEOGRAPHIC_LAYERS
from app.utils.authentication import get_current_user

router = APIRouter(prefix="/gis", tags=["GIS"])
GIS_DATA_ROOT = Path(__file__).resolve().parents[3] / "gis" / "data" / "geographic_data"

GeoJsonLayerName = Literal[
    "administrative_boundaries",
    "lakes",
    "land_use",
    "rivers",
    "roads",
    "watersheds",
]


@router.get("/layers/{layer_name}")
def geojson_layer(
    layer_name: GeoJsonLayerName,
    _user: User = Depends(get_current_user),
) -> FileResponse:
    data_root = GIS_DATA_ROOT.resolve()
    layer_path = (data_root / GEOGRAPHIC_LAYERS[layer_name]).resolve()
    try:
        layer_path.relative_to(data_root)
    except ValueError:
        raise HTTPException(status_code=404, detail="GIS layer not found.") from None
    if not layer_path.is_file():
        raise HTTPException(status_code=404, detail="GIS layer is unavailable.")
    return FileResponse(
        layer_path,
        media_type="application/geo+json",
        headers={"Cache-Control": "private, max-age=300"},
    )


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
                    "verification_status": "unverified_saved_record",
                    "created_at": item.created_at.isoformat(),
                },
            }
            for item in records
        ],
    }