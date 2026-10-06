import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def save_results(results: list[Any], output_path: str | Path) -> Path:
    """Write simulation results to a JSON file with UTC creation metadata."""
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "result_count": len(results),
        "results": [result.to_dict() if hasattr(result, "to_dict") else result for result in results],
        "note": "Scenario estimates only; not an official warning or operational forecast.",
    }
    with destination.open("w", encoding="utf-8") as result_file:
        json.dump(payload, result_file, indent=2, allow_nan=False)
    return destination


def load_results(input_path: str | Path) -> dict[str, Any]:
    """Load and minimally validate a saved simulation-results document."""
    with Path(input_path).open(encoding="utf-8") as result_file:
        payload = json.load(result_file)
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise ValueError("Simulation result file must contain a JSON 'results' list.")
    if payload.get("result_count") != len(payload["results"]):
        raise ValueError("Simulation result_count does not match the stored results.")
    return payload
