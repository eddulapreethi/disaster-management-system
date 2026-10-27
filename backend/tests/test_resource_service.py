from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.connection import Base
from app.models.resource import Resource
from app.schemas.resource import ResourceCreate, ResourcePlanRequest, ResourceUpdate
from app.services import resource_service


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def add_resource(db: Session, name: str, quantity: int, *, longitude: float = 76.0) -> Resource:
    return resource_service.create_resource(
        db,
        ResourceCreate(
            name=name,
            resource_type="water",
            quantity=quantity,
            unit="litres",
            latitude=10.0,
            longitude=longitude,
        ),
    )


def test_direct_allocation_is_conditional_and_marks_fully_used_stock_depleted(db: Session) -> None:
    resource = add_resource(db, "Depot", 5)

    with pytest.raises(HTTPException) as raised:
        resource_service.allocate_resource(db, resource.id, 6)

    assert raised.value.status_code == 409
    assert db.get(Resource, resource.id).quantity == 5

    updated = resource_service.allocate_resource(db, resource.id, 5)
    assert updated.quantity == 0
    assert updated.status == "depleted"


def test_allocation_plan_deducts_stock_and_reports_shortage(db: Session) -> None:
    resource = add_resource(db, "Depot", 5)
    demand = {
        "id": "shelter-a",
        "resource_type": "water",
        "quantity": 7,
        "unit": "litres",
        "latitude": 10.0,
        "longitude": 76.0,
        "priority_score": 70,
    }

    result = resource_service.plan_resource_allocation(db, [demand])

    allocation = result["allocations"][0]
    assert (allocation["allocated"], allocation["shortage"]) == (5, 2)
    assert db.get(Resource, resource.id).quantity == 0
    assert db.get(Resource, resource.id).status == "depleted"


def test_duplicate_demand_ids_are_rejected_before_inventory_changes(db: Session) -> None:
    resource = add_resource(db, "Depot", 5)
    demands = [
        {
            "id": "same-id",
            "resource_type": "water",
            "quantity": 1,
            "latitude": 10.0,
            "longitude": 76.0,
        },
        {
            "id": "same-id",
            "resource_type": "water",
            "quantity": 1,
            "latitude": 10.0,
            "longitude": 76.0,
        },
    ]

    with pytest.raises(ValueError, match="unique"):
        resource_service.plan_resource_allocation(db, demands)

    assert db.get(Resource, resource.id).quantity == 5
    with pytest.raises(ValueError, match="unique"):
        ResourcePlanRequest(demands=demands)


def test_plan_rolls_back_prior_stock_updates_when_a_later_reservation_loses_race(db: Session) -> None:
    first = add_resource(db, "Near depot", 2, longitude=76.0)
    second = add_resource(db, "Far depot", 2, longitude=77.0)
    demand = {
        "id": "shelter-a",
        "resource_type": "water",
        "quantity": 3,
        "unit": "litres",
        "latitude": 10.0,
        "longitude": 76.0,
        "priority_score": 70,
    }
    execute = db.execute
    update_count = 0

    def race_on_second_update(statement, *args, **kwargs):
        nonlocal update_count
        update_count += 1
        if update_count == 2:
            return type("FailedUpdate", (), {"rowcount": 0})()
        return execute(statement, *args, **kwargs)

    with patch.object(db, "execute", side_effect=race_on_second_update):
        with pytest.raises(ValueError, match="Inventory changed"):
            resource_service.plan_resource_allocation(db, [demand])

    db.expire_all()
    assert db.get(Resource, first.id).quantity == 2
    assert db.get(Resource, second.id).quantity == 2


def test_resource_update_resets_status_and_delete_removes_record(db: Session) -> None:
    resource = add_resource(db, "Depot", 5)

    updated = resource_service.update_resource(
        db,
        resource.id,
        ResourceUpdate(quantity=0),
    )
    assert updated.status == "depleted"

    resource_service.delete_resource(db, resource.id)
    assert db.scalar(select(Resource.id).where(Resource.id == resource.id)) is None


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [(-90, -180), (90, 180), (0, 0)],
)
def test_resource_coordinate_boundaries_are_valid(latitude: float, longitude: float) -> None:
    data = ResourceCreate(
        name="Boundary depot",
        resource_type="water",
        quantity=1,
        latitude=latitude,
        longitude=longitude,
    )
    assert data.latitude == latitude
    assert data.longitude == longitude


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [(90.001, 0), (-90.001, 0), (0, 180.001), (0, -180.001), (float("nan"), 0), (0, float("inf"))],
)
def test_resource_create_rejects_invalid_coordinates(latitude: float, longitude: float) -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ResourceCreate(
            name="Invalid depot",
            resource_type="water",
            quantity=1,
            latitude=latitude,
            longitude=longitude,
        )


@pytest.mark.parametrize(
    "values",
    [
        {"id": " ", "resource_type": "water", "quantity": 1, "latitude": 0, "longitude": 0},
        {"id": "demand", "resource_type": " ", "quantity": 1, "latitude": 0, "longitude": 0},
        {"id": "demand", "resource_type": "water", "unit": " ", "quantity": 1, "latitude": 0, "longitude": 0},
    ],
)
def test_resource_demand_rejects_blank_identifiers_and_labels(values: dict) -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ResourcePlanRequest(demands=[values])


def test_resource_database_constraints_reject_invalid_orm_writes(db: Session) -> None:
    db.add(Resource(
        name="Invalid depot",
        resource_type="water",
        quantity=-1,
        unit="litres",
        latitude=91,
        longitude=0,
        status="available",
    ))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_zero_demand_is_rejected_before_inventory_changes(db: Session) -> None:
    resource = add_resource(db, "Depot", 5)
    demand = {
        "id": "shelter-a",
        "resource_type": "water",
        "quantity": 0,
        "latitude": 10.0,
        "longitude": 76.0,
    }

    with pytest.raises(ValueError, match="greater than zero"):
        resource_service.plan_resource_allocation(db, [demand])
    assert db.get(Resource, resource.id).quantity == 5
