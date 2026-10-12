from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.models.user import User
from app.schemas.resource import (
    AllocationRequest,
    ResourceCreate,
    ResourcePlanRequest,
    ResourceRead,
    ResourceUpdate,
)
from app.services.resource_service import (
    allocate_resource,
    create_resource,
    delete_resource,
    list_resources,
    plan_resource_allocation,
    update_resource,
)
from app.utils.authentication import get_current_user

router = APIRouter(prefix="/resources", tags=["resources"])


@router.get("", response_model=list[ResourceRead])
def get_resources(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return list_resources(db)


@router.post("", response_model=ResourceRead, status_code=status.HTTP_201_CREATED)
def post_resource(
    data: ResourceCreate,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return create_resource(db, data)


@router.patch("/{resource_id}", response_model=ResourceRead)
def patch_resource(
    resource_id: int,
    data: ResourceUpdate,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return update_resource(db, resource_id, data)


@router.delete("/{resource_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_resource(
    resource_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    delete_resource(db, resource_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/allocate", response_model=ResourceRead)
def post_allocation(
    data: AllocationRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return allocate_resource(db, data.resource_id, data.quantity)


@router.post("/plan")
def post_resource_plan(
    data: ResourcePlanRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    try:
        return plan_resource_allocation(db, [demand.model_dump() for demand in data.demands])
    except (ValueError, KeyError) as error:
        from fastapi import HTTPException

        raise HTTPException(status_code=409, detail=str(error)) from error