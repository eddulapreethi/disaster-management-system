from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.models.simulation import Simulation
from app.models.user import User
from app.services.simulation_service import SimulationInput, run_simulation
from app.utils.authentication import get_current_user

router = APIRouter(prefix="/simulations", tags=["simulations"])


@router.post("")
def simulate(
    data: SimulationInput,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    result = run_simulation(data)
    record = Simulation(
        user_id=_user.id,
        disaster_type=data.disaster_type,
        scenario=result["scenario_name"],
        parameters=data.model_dump(),
        results=result,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return {"simulation_id": record.id, **result}


@router.get("")
def simulation_history(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    records = db.scalars(
        select(Simulation)
        .where(Simulation.user_id == user.id)
        .order_by(Simulation.created_at.desc())
    ).all()
    return [
        {
            "id": record.id,
            "disaster_type": record.disaster_type,
            "scenario": record.scenario,
            "parameters": record.parameters,
            "results": record.results,
            "created_at": record.created_at.isoformat(),
        }
        for record in records
    ]