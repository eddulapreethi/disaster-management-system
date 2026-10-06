from __future__ import annotations

import math
import threading
from dataclasses import dataclass
from typing import Any


@dataclass
class ResourceRecord:
    """Portable resource record compatible with the backend Resource model."""

    id: int
    name: str
    resource_type: str
    quantity: int
    unit: str
    latitude: float
    longitude: float
    status: str = "available"

    def __post_init__(self) -> None:
        if self.id <= 0:
            raise ValueError("Resource id must be positive.")
        if not self.name.strip() or not self.resource_type.strip() or not self.unit.strip():
            raise ValueError("Resource name, type and unit cannot be blank.")
        if self.quantity < 0:
            raise ValueError("Resource quantity cannot be negative.")
        if not math.isfinite(self.latitude) or not -90 <= self.latitude <= 90:
            raise ValueError("Resource latitude must be between -90 and 90.")
        if not math.isfinite(self.longitude) or not -180 <= self.longitude <= 180:
            raise ValueError("Resource longitude must be between -180 and 180.")

    @classmethod
    def from_object(cls, value: Any) -> ResourceRecord:
        """Copy an ORM model, Pydantic model, or mapping into a portable record."""
        getter = value.get if isinstance(value, dict) else lambda key, default=None: getattr(value, key, default)
        return cls(
            id=int(getter("id")),
            name=str(getter("name")),
            resource_type=str(getter("resource_type")),
            quantity=int(getter("quantity")),
            unit=str(getter("unit", "units")),
            latitude=float(getter("latitude")),
            longitude=float(getter("longitude")),
            status=str(getter("status", "available")),
        )


class InventoryStore:
    """Thread-safe in-memory inventory for planning; not a replacement for persistence."""

    def __init__(self, resources: list[ResourceRecord] | None = None) -> None:
        self._lock = threading.RLock()
        self._resources: dict[int, ResourceRecord] = {}
        for resource in resources or []:
            if resource.id in self._resources:
                raise ValueError(f"Duplicate resource id: {resource.id}")
            self._resources[resource.id] = resource

    def list_resources(self, resource_type: str | None = None) -> list[ResourceRecord]:
        """Return copied resources, optionally filtered by type and availability."""
        with self._lock:
            items = self._resources.values()
            return [
                ResourceRecord(**vars(resource))
                for resource in items
                if resource.quantity > 0
                and resource.status.lower() == "available"
                and (resource_type is None or resource.resource_type.casefold() == resource_type.casefold())
            ]

    def reserve(self, resource_id: int, quantity: int) -> ResourceRecord:
        """Atomically decrement stock, rejecting over-allocation."""
        if quantity <= 0:
            raise ValueError("Reservation quantity must be positive.")
        with self._lock:
            resource = self._resources.get(resource_id)
            if resource is None:
                raise KeyError(f"Resource {resource_id} was not found.")
            if resource.status.lower() != "available" or quantity > resource.quantity:
                raise ValueError(f"Resource {resource_id} does not have {quantity} available units.")
            resource.quantity -= quantity
            if resource.quantity == 0:
                resource.status = "depleted"
            return ResourceRecord(**vars(resource))
