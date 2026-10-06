from collections.abc import Sequence
from typing import Any

from gis.gis_processing import haversine_distance_km


def optimize_visit_order(
    origin: tuple[float, float],
    destinations: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    """Greedily order destination points by nearest great-circle distance.

    Coordinates are (latitude, longitude). Distances are straight-line estimates,
    not road routes or travel-time predictions.
    """
    current_latitude, current_longitude = origin
    if not (-90 <= current_latitude <= 90 and -180 <= current_longitude <= 180):
        raise ValueError("Origin must be a valid (latitude, longitude) pair.")

    pending = []
    seen_ids: set[str] = set()
    for destination in destinations:
        name = str(destination.get("name", "")).strip()
        identifier = str(destination.get("id", name))
        latitude = float(destination["latitude"])
        longitude = float(destination["longitude"])
        if not name:
            raise ValueError("Every destination must have a non-empty name.")
        if identifier in seen_ids:
            raise ValueError(f"Duplicate destination id: {identifier}")
        seen_ids.add(identifier)
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise ValueError(f"Destination {name!r} has invalid coordinates.")
        pending.append({**destination, "id": identifier, "name": name, "latitude": latitude, "longitude": longitude})

    ordered = []
    total_distance = 0.0
    while pending:
        nearest = min(
            pending,
            key=lambda item: haversine_distance_km(
                current_longitude,
                current_latitude,
                item["longitude"],
                item["latitude"],
            ),
        )
        distance = haversine_distance_km(
            current_longitude,
            current_latitude,
            nearest["longitude"],
            nearest["latitude"],
        )
        total_distance += distance
        ordered.append({**nearest, "distance_from_previous_km": round(distance, 3)})
        current_latitude, current_longitude = nearest["latitude"], nearest["longitude"]
        pending.remove(nearest)

    return {
        "stops": ordered,
        "total_distance_km": round(total_distance, 3),
        "method": "nearest-neighbour great-circle estimate; not a road route",
    }
