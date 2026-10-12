import importlib
import sys
from pathlib import Path

from sqlalchemy import case, select, update
from sqlalchemy.orm import Session

from app.models.resource import Resource
from app.schemas.resource import ResourceCreate, ResourceUpdate
from app.utils.validation import validate_resource_quantity


def create_resource(db: Session, data: ResourceCreate) -> Resource:
    resource = Resource(**data.model_dump())
    db.add(resource)
    db.commit()
    db.refresh(resource)
    return resource


def list_resources(db: Session) -> list[Resource]:
    return list(db.scalars(select(Resource).order_by(Resource.name)).all())


def update_resource(db: Session, resource_id: int, data: ResourceUpdate) -> Resource:
    resource = db.get(Resource, resource_id)
    if resource is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Resource not found.")

    changes = data.model_dump(exclude_unset=True)
    if "quantity" in changes:
        changes["status"] = "depleted" if changes["quantity"] == 0 else "available"
    for field, value in changes.items():
        setattr(resource, field, value)
    db.commit()
    db.refresh(resource)
    return resource


def delete_resource(db: Session, resource_id: int) -> None:
    resource = db.get(Resource, resource_id)
    if resource is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Resource not found.")
    db.delete(resource)
    db.commit()


def allocate_resource(db: Session, resource_id: int, quantity: int) -> Resource:
    from fastapi import HTTPException

    if quantity <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be greater than zero.")
    result = db.execute(
        update(Resource)
        .where(
            Resource.id == resource_id,
            Resource.status == "available",
            Resource.quantity >= quantity,
        )
        .values(
            quantity=Resource.quantity - quantity,
            status=case((Resource.quantity == quantity, "depleted"), else_=Resource.status),
        )
    )
    if result.rowcount != 1:
        resource = db.get(Resource, resource_id)
        if resource is None:
            db.rollback()
            raise HTTPException(status_code=404, detail="Resource not found.")
        db.rollback()
        if resource.status != "available":
            raise HTTPException(status_code=409, detail="Resource is not available for allocation.")
        validate_resource_quantity(resource.quantity, quantity)
        raise HTTPException(status_code=409, detail="Inventory changed; reload and try again.")
    db.commit()
    return db.get(Resource, resource_id)


def plan_resource_allocation(db: Session, demands: list[dict]) -> dict:
    """Plan against current persisted inventory and atomically apply reservations."""
    demand_ids = [str(demand.get("id", index)) for index, demand in enumerate(demands)]
    if len(demand_ids) != len(set(demand_ids)):
        raise ValueError("Demand IDs must be unique within a resource plan.")
    project_root = str(Path(__file__).resolve().parents[3])
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    database_module = importlib.import_module("resource-optimization.resource_database")
    allocation_module = importlib.import_module("resource-optimization.resource_allocation")
    routing_module = importlib.import_module("resource-optimization.route_optimization")

    resource_rows = list_resources(db)
    inventory = database_module.InventoryStore(
        [database_module.ResourceRecord.from_object(resource) for resource in resource_rows]
    )
    plan = allocation_module.allocate_resources(demands, inventory)
    resources_by_id = {resource.id: resource for resource in resource_rows}
    demands_by_id = {str(demand.get("id", index)): demand for index, demand in enumerate(demands)}
    for demand_result in plan["allocations"]:
        demand = demands_by_id[demand_result["demand_id"]]
        stops = [
            {
                "id": source["resource_id"],
                "name": source["name"],
                "latitude": resources_by_id[source["resource_id"]].latitude,
                "longitude": resources_by_id[source["resource_id"]].longitude,
            }
            for source in demand_result["sources"]
        ]
        demand_result["pickup_route"] = routing_module.optimize_visit_order(
            (float(demand["latitude"]), float(demand["longitude"])),
            stops,
        )
    try:
        for demand_result in plan["allocations"]:
            for source in demand_result["sources"]:
                quantity = source["quantity"]
                result = db.execute(
                    update(Resource)
                    .where(
                        Resource.id == source["resource_id"],
                        Resource.status == "available",
                        Resource.quantity >= quantity,
                    )
                    .values(
                        quantity=Resource.quantity - quantity,
                        status=case(
                            (Resource.quantity == quantity, "depleted"),
                            else_=Resource.status,
                        ),
                    )
                )
                if result.rowcount != 1:
                    raise ValueError("Inventory changed while planning; reload resources and retry.")
        db.commit()
    except Exception:
        db.rollback()
        raise
    return plan