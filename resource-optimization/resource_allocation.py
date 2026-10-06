from collections.abc import Mapping, Sequence
from typing import Any

from gis.gis_processing import haversine_distance_km

from .resource_database import InventoryStore


def allocate_resources(
    demands: Sequence[Mapping[str, Any]],
    inventory: InventoryStore,
) -> dict[str, Any]:
    """Allocate available stock by descending priority, then nearest depot.

    Each demand mapping must include resource_type, quantity, latitude and
    longitude. Optional keys are id, priority_score and unit. The inventory is
    decremented as allocations are made.
    """
    normalized = []
    for index, demand in enumerate(demands):
        resource_type = str(demand.get("resource_type", "")).strip()
        if not resource_type:
            raise ValueError(f"Demand at index {index} has no resource_type.")
        quantity = int(demand.get("quantity", 0))
        if quantity < 0:
            raise ValueError(f"Demand at index {index} has negative quantity.")
        latitude = float(demand["latitude"])
        longitude = float(demand["longitude"])
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise ValueError(f"Demand at index {index} has invalid coordinates.")
        priority_score = float(demand.get("priority_score", 0.0))
        if not 0 <= priority_score <= 100:
            raise ValueError(f"Demand at index {index} priority_score must be between 0 and 100.")
        normalized.append(
            {
                **demand,
                "id": str(demand.get("id", index)),
                "resource_type": resource_type,
                "quantity": quantity,
                "latitude": latitude,
                "longitude": longitude,
                "priority_score": priority_score,
                "_position": index,
            }
        )

    normalized.sort(key=lambda item: (-item["priority_score"], item["_position"]))
    allocations: list[dict[str, Any]] = []
    for demand in normalized:
        remaining = demand["quantity"]
        if remaining == 0:
            allocations.append(_demand_result(demand, [], 0))
            continue

        candidates = inventory.list_resources(demand["resource_type"])
        candidates.sort(
            key=lambda resource: (
                haversine_distance_km(
                    demand["longitude"],
                    demand["latitude"],
                    resource.longitude,
                    resource.latitude,
                ),
                resource.id,
            )
        )
        chosen = []
        for resource in candidates:
            if remaining == 0:
                break
            if demand.get("unit") and resource.unit.casefold() != str(demand["unit"]).casefold():
                continue
            amount = min(remaining, resource.quantity)
            try:
                reserved = inventory.reserve(resource.id, amount)
            except (KeyError, ValueError):
                continue
            distance = haversine_distance_km(
                demand["longitude"],
                demand["latitude"],
                reserved.longitude,
                reserved.latitude,
            )
            chosen.append(
                {
                    "resource_id": reserved.id,
                    "name": reserved.name,
                    "quantity": amount,
                    "unit": reserved.unit,
                    "distance_km": round(distance, 3),
                }
            )
            remaining -= amount
        allocations.append(_demand_result(demand, chosen, remaining))

    return {
        "allocations": allocations,
        "request_count": len(normalized),
        "fully_fulfilled_count": sum(item["shortage"] == 0 for item in allocations),
        "total_shortage": sum(item["shortage"] for item in allocations),
        "note": "Planning aid only. Confirm stock, access, safety and incident-command priorities before dispatch.",
    }


def _demand_result(
    demand: Mapping[str, Any],
    sources: list[dict[str, Any]],
    shortage: int,
) -> dict[str, Any]:
    allocated = sum(source["quantity"] for source in sources)
    return {
        "demand_id": demand["id"],
        "resource_type": demand["resource_type"],
        "requested": demand["quantity"],
        "allocated": allocated,
        "shortage": shortage,
        "priority_score": demand["priority_score"],
        "sources": sources,
    }
