from collections.abc import Sequence
from typing import Any


def build_authority_notifications(
    alert: dict[str, Any],
    authority_ids: Sequence[str | int],
) -> list[dict[str, Any]]:
    """Build authority notification payloads with prediction context."""
    return [
        {
            "recipient_id": str(authority_id),
            "audience": "authority",
            "channel": "in_app",
            "alert_id": alert["alert_id"],
            "title": alert["title"],
            "message": alert["message"],
            "severity": alert["severity"],
            "disaster_type": alert["disaster_type"],
            "risk_score": float(alert["risk_score"]),
            "location": _location(alert),
            "is_official_warning": False,
            "delivery_status": "pending",
        }
        for authority_id in authority_ids
    ]


def _location(alert: dict[str, Any]) -> dict[str, float] | None:
    latitude = alert.get("latitude")
    longitude = alert.get("longitude")
    if latitude is None or longitude is None:
        return None
    return {"latitude": float(latitude), "longitude": float(longitude)}
