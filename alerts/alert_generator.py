from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from .alert_rules import AlertDecision, evaluate_alert_rule


@dataclass(frozen=True)
class EmergencyAlert:
    alert_id: str
    title: str
    message: str
    severity: str
    disaster_type: str
    risk_score: float
    latitude: float | None
    longitude: float | None
    created_at: str
    rule_reason: str
    is_official_warning: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_backend_payload(self) -> dict[str, Any]:
        """Return fields accepted by backend.schemas.alert.AlertCreate."""
        return {
            "title": self.title,
            "message": self.message,
            "severity": self.severity,
            "disaster_type": self.disaster_type,
            "latitude": self.latitude,
            "longitude": self.longitude,
        }


def generate_alert(
    prediction: dict[str, Any],
    *,
    minimum_alert_score: float = 30.0,
) -> tuple[EmergencyAlert | None, AlertDecision]:
    """Generate an alert from a prediction payload; returns None below threshold."""
    disaster_type = str(prediction.get("disaster_type", "")).strip().lower()
    if disaster_type not in {"flood", "wildfire", "storm"}:
        raise ValueError("prediction disaster_type must be flood, wildfire, or storm.")

    raw_score = prediction.get("risk_score")
    if raw_score is None and prediction.get("flood_probability") is not None:
        raw_score = float(prediction["flood_probability"]) * 100
    if raw_score is None:
        raise ValueError("prediction must contain risk_score or flood_probability.")
    risk_score = float(raw_score)
    decision = evaluate_alert_rule(risk_score, minimum_alert_score=minimum_alert_score)
    if not decision.should_alert:
        return None, decision

    latitude = _optional_coordinate(prediction.get("latitude"), -90, 90, "latitude")
    longitude = _optional_coordinate(prediction.get("longitude"), -180, 180, "longitude")
    title = f"{decision.severity.title()} {disaster_type} risk alert"
    message = (
        f"Automated {disaster_type} risk estimate: {risk_score:.1f}/100 "
        f"({decision.severity}). This is not an official warning. Check local authority alerts."
    )
    alert = EmergencyAlert(
        alert_id=str(uuid4()),
        title=title,
        message=message,
        severity=decision.severity,
        disaster_type=disaster_type,
        risk_score=risk_score,
        latitude=latitude,
        longitude=longitude,
        created_at=datetime.now(timezone.utc).isoformat(),
        rule_reason=decision.reason,
    )
    return alert, decision


def _optional_coordinate(value: Any, minimum: float, maximum: float, label: str) -> float | None:
    if value is None:
        return None
    coordinate = float(value)
    if not minimum <= coordinate <= maximum:
        raise ValueError(f"{label} must be between {minimum} and {maximum}.")
    return coordinate
