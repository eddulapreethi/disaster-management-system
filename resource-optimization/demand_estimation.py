from dataclasses import dataclass


@dataclass(frozen=True)
class DemandEstimate:
    resource_type: str
    quantity: int
    unit: str
    exposed_people: int
    duration_days: int
    assumptions: str


def estimate_demand(
    resource_type: str,
    exposed_people: int,
    *,
    duration_days: int = 1,
    buffer_percent: float = 10.0,
) -> DemandEstimate:
    """Estimate essential supply using transparent per-person planning rates.

    Water: 3 litres/person/day; food kits: 1 kit/person/day; shelter spaces:
    1/person total; medical kits: 1 kit/20 people/day (minimum one if exposed).
    Other resource types must specify a supported unit rate by adding a policy.
    """
    if not resource_type.strip():
        raise ValueError("resource_type cannot be blank.")
    if exposed_people < 0 or duration_days < 1:
        raise ValueError("exposed_people must be non-negative and duration_days at least 1.")
    if not 0 <= buffer_percent <= 100:
        raise ValueError("buffer_percent must be between 0 and 100.")

    key = resource_type.strip().casefold().replace("_", " ").replace("-", " ")
    policies = {
        "water": (3.0, "litres", True, "3 litres per person per day"),
        "food": (1.0, "kits", True, "1 food kit per person per day"),
        "food kit": (1.0, "kits", True, "1 food kit per person per day"),
        "shelter": (1.0, "spaces", False, "1 shelter space per exposed person"),
        "shelter space": (1.0, "spaces", False, "1 shelter space per exposed person"),
        "medical": (1.0 / 20.0, "kits", True, "1 medical kit per 20 people per day, minimum 1"),
        "medical kit": (1.0 / 20.0, "kits", True, "1 medical kit per 20 people per day, minimum 1"),
    }
    policy = policies.get(key)
    if policy is None:
        raise ValueError(f"No demand policy defined for resource type {resource_type!r}.")
    rate, unit, scales_with_duration, assumption = policy
    days = duration_days if scales_with_duration else 1
    base_quantity = exposed_people * rate * days
    if key in {"medical", "medical kit"} and exposed_people > 0:
        base_quantity = max(1.0, base_quantity)
    total = int((base_quantity * (1 + buffer_percent / 100.0)) + 0.999999)
    return DemandEstimate(
        resource_type=resource_type.strip(),
        quantity=total,
        unit=unit,
        exposed_people=exposed_people,
        duration_days=duration_days,
        assumptions=f"{assumption}; {buffer_percent:g}% planning buffer.",
    )
