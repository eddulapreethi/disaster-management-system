from collections.abc import Sequence
from typing import Any


def build_response_team_notifications(
    alert: dict[str, Any],
    team_ids: Sequence[str | int],
) -> list[dict[str, Any]]:
    """Build response-team task notifications; dispatch requires a configured adapter."""
    return [
        {
            "recipient_id": str(team_id),
            "audience": "response_team",
            "channel": "in_app",
            "alert_id": alert["alert_id"],
            "title": alert["title"],
            "message": alert["message"],
            "severity": alert["severity"],
            "disaster_type": alert["disaster_type"],
            "location": _location(alert),
            "dispatch_authorized": False,
            "delivery_status": "pending",
        }
        for team_id in team_ids
    ]


def _location(alert: dict[str, Any]) -> dict[str, float] | None:
    latitude = alert.get("latitude")
    longitude = alert.get("longitude")
    if latitude is None or longitude is None:
        return None
    return {"latitude": float(latitude), "longitude": float(longitude)}
