import importlib
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.resource import Resource
from app.schemas.resource import ResourceCreate
from app.utils.validation import validate_resource_quantity


def create_resource(db: Session, data: ResourceCreate) -> Resource:
    resource = Resource(**data.model_dump())
    db.add(resource)
    db.commit()
    db.refresh(resource)
    return resource


def list_resources(db: Session) -> list[Resource]:
    return list(db.scalars(select(Resource).order_by(Resource.name)).all())


def allocate_resource(db: Session, resource_id: int, quantity: int) -> Resource:
    resource = db.get(Resource, resource_id)
    if resource is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Resource not found.")

    validate_resource_quantity(resource.quantity, quantity)
    resource.quantity -= quantity
    if resource.quantity == 0:
        resource.status = "depleted"
    db.commit()
    db.refresh(resource)
    return resource


def plan_resource_allocation(db: Session, demands: list[dict]) -> dict:
    """Plan against current persisted inventory and atomically apply reservations."""
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
                resource = db.get(Resource, source["resource_id"], with_for_update=True)
                if resource is None or resource.quantity < source["quantity"]:
                    raise ValueError("Inventory changed while planning; reload resources and retry.")
                resource.quantity -= source["quantity"]
                if resource.quantity == 0:
                    resource.status = "depleted"
        db.commit()
    except Exception:
        db.rollback()
        raise
    return plan