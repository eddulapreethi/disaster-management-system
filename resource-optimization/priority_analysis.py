from dataclasses import dataclass


@dataclass(frozen=True)
class PriorityFactors:
    severity: int
    exposed_people: int
    vulnerability: float = 0.0
    time_to_impact_hours: float | None = None


def calculate_priority(factors: PriorityFactors) -> tuple[float, str]:
    """Score response priority from transparent 0..100 weighted inputs.

    Severity is 1..5, vulnerability is 0..1, and shorter lead time increases
    urgency. This is a planning aid, not a substitute for incident command.
    """
    if not 1 <= factors.severity <= 5:
        raise ValueError("severity must be an integer between 1 and 5.")
    if factors.exposed_people < 0:
        raise ValueError("exposed_people cannot be negative.")
    if not 0 <= factors.vulnerability <= 1:
        raise ValueError("vulnerability must be between 0 and 1.")
    if factors.time_to_impact_hours is not None and factors.time_to_impact_hours < 0:
        raise ValueError("time_to_impact_hours cannot be negative.")

    severity_score = (factors.severity - 1) / 4 * 40
    population_score = min(1.0, factors.exposed_people / 10_000) * 30
    vulnerability_score = factors.vulnerability * 20
    if factors.time_to_impact_hours is None:
        urgency_score = 0.0
    else:
        urgency_score = max(0.0, 10.0 * (1.0 - min(factors.time_to_impact_hours, 24.0) / 24.0))
    score = round(min(100.0, severity_score + population_score + vulnerability_score + urgency_score), 2)
    band = "low" if score < 30 else "moderate" if score < 60 else "high" if score < 80 else "critical"
    return score, band
