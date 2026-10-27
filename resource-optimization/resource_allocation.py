from collections.abc import Mapping, Sequence
import math
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
        raw_quantity = demand.get("quantity", 0)
        if isinstance(raw_quantity, bool) or not isinstance(raw_quantity, int):
            raise ValueError(f"Demand at index {index} quantity must be an integer.")
        quantity = raw_quantity
        if quantity <= 0:
            raise ValueError(f"Demand at index {index} quantity must be greater than zero.")
        if isinstance(demand["latitude"], bool) or isinstance(demand["longitude"], bool):
            raise ValueError(f"Demand at index {index} has invalid coordinates.")
        latitude = float(demand["latitude"])
        longitude = float(demand["longitude"])
        if (
            not math.isfinite(latitude)
            or not math.isfinite(longitude)
            or not (-90 <= latitude <= 90 and -180 <= longitude <= 180)
        ):
            raise ValueError(f"Demand at index {index} has invalid coordinates.")
        raw_priority = demand.get("priority_score", 0.0)
        if isinstance(raw_priority, bool):
            raise ValueError(f"Demand at index {index} priority_score must be numeric.")
        priority_score = float(raw_priority)
        if not math.isfinite(priority_score) or not 0 <= priority_score <= 100:
            raise ValueError(f"Demand at index {index} priority_score must be between 0 and 100.")
        demand_id = str(demand.get("id", index)).strip()
        if not demand_id:
            raise ValueError(f"Demand at index {index} has a blank id.")
        unit = demand.get("unit")
        if unit is not None:
            unit = str(unit).strip()
            if not unit:
                raise ValueError(f"Demand at index {index} has a blank unit.")
        normalized.append(
            {
                **demand,
                "id": demand_id,
                "resource_type": resource_type,
                "quantity": quantity,
                "latitude": latitude,
                "longitude": longitude,
                "priority_score": priority_score,
                "unit": unit,
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
