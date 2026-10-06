import importlib
import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.models.user import User
from app.utils.authentication import get_current_user

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


class RecommendationRequest(BaseModel):
    prediction: dict[str, Any] | None = None
    simulation: dict[str, Any] | None = None


@router.post("")
def create_recommendations(
    data: RecommendationRequest,
    _user: User = Depends(get_current_user),
):
    if data.prediction is None and data.simulation is None:
        raise HTTPException(status_code=422, detail="Provide a prediction or simulation result.")

    project_root = str(Path(__file__).resolve().parents[3])
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    try:
        response_module = importlib.import_module("ai-assistant.response_generator")
        if data.prediction is not None:
            return response_module.generate_response(
                data.prediction,
                simulation=data.simulation,
            )
        return response_module.generate_scenario_response(data.simulation)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
