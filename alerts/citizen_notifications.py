from collections.abc import Sequence
from typing import Any


def build_citizen_notifications(
    alert: dict[str, Any],
    citizen_ids: Sequence[str | int],
) -> list[dict[str, Any]]:
    """Build in-app citizen notification payloads without sending them."""
    return [
        {
            "recipient_id": str(citizen_id),
            "audience": "citizen",
            "channel": "in_app",
            "alert_id": alert["alert_id"],
            "title": alert["title"],
            "message": alert["message"],
            "severity": alert["severity"],
            "disaster_type": alert["disaster_type"],
            "location": _location(alert),
            "delivery_status": "pending",
        }
        for citizen_id in citizen_ids
    ]


def _location(alert: dict[str, Any]) -> dict[str, float] | None:
    latitude = alert.get("latitude")
    longitude = alert.get("longitude")
    if latitude is None or longitude is None:
        return None
    return {"latitude": float(latitude), "longitude": float(longitude)}
