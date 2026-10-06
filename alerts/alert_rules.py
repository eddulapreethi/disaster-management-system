from dataclasses import dataclass
from typing import Literal

RiskLevel = Literal["low", "moderate", "high", "critical"]


@dataclass(frozen=True)
class AlertDecision:
    should_alert: bool
    severity: RiskLevel
    reason: str


THRESHOLDS: tuple[tuple[float, RiskLevel], ...] = (
    (80.0, "critical"),
    (60.0, "high"),
    (30.0, "moderate"),
    (0.0, "low"),
)


def classify_risk_score(score: float) -> RiskLevel:
    """Map the backend's 0..100 risk score to its accepted alert severity."""
    if not 0 <= score <= 100:
        raise ValueError("risk score must be between 0 and 100.")
    for threshold, level in THRESHOLDS:
        if score >= threshold:
            return level
    return "low"


def evaluate_alert_rule(
    risk_score: float,
    *,
    minimum_alert_score: float = 30.0,
) -> AlertDecision:
    """Decide whether to generate an alert; low scores remain dashboard-only."""
    if not 0 <= risk_score <= 100:
        raise ValueError("risk score must be between 0 and 100.")
    if not 0 <= minimum_alert_score <= 100:
        raise ValueError("minimum_alert_score must be between 0 and 100.")
    severity = classify_risk_score(risk_score)
    should_alert = risk_score >= minimum_alert_score
    reason = (
        f"Risk score {risk_score:.2f} meets the alert threshold {minimum_alert_score:.2f}."
        if should_alert
        else f"Risk score {risk_score:.2f} is below the alert threshold {minimum_alert_score:.2f}."
    )
    return AlertDecision(should_alert=should_alert, severity=severity, reason=reason)
