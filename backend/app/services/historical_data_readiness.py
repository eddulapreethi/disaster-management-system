import csv
import hashlib
import json
import sys
import threading
import time
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PROJECT_ROOT_STRING = str(PROJECT_ROOT)
if PROJECT_ROOT_STRING not in sys.path:
    sys.path.insert(0, PROJECT_ROOT_STRING)

from ml.preprocessing.historical_analytics import build_historical_analytics
from ml.preprocessing.file_integrity import sha256_file

_CACHE_TTL_SECONDS = 30.0
_CACHE_LOCK = threading.RLock()
_CACHE: dict[tuple[str, str], tuple[float, dict[str, Any]]] = {}


def _dataset_fingerprint(project_root: Path) -> str:
    root = project_root.resolve()
    candidates = []
    for subdir in (
        root / "ml" / "datasets" / "historical_data" / "processed",
        root / "ml" / "datasets" / "historical_disasters" / "EM-DAT",
    ):
        if not subdir.exists():
            continue
        for path in sorted(subdir.rglob("*")):
            if path.is_file():
                stat = path.stat()
                candidates.append((str(path.relative_to(root)), stat.st_size, stat.st_mtime_ns))
    digest = sha256()
    for entry in candidates:
        digest.update(str(entry).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _get_cached_value(cache_key: tuple[str, str], factory):
    now = time.monotonic()
    with _CACHE_LOCK:
        cached = _CACHE.get(cache_key)
        if cached and now - cached[0] < _CACHE_TTL_SECONDS:
            return deepcopy(cached[1])
    value = factory()
    with _CACHE_LOCK:
        _CACHE[cache_key] = (now, value)
    return deepcopy(value)


def _sha256(path: Path) -> str:
    return sha256_file(path)


def get_historical_data_readiness(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    cache_key = ("historical_data_readiness", str(root), _dataset_fingerprint(root))

    def build_result() -> dict[str, Any]:
        datasets_root = root / "ml" / "datasets" / "historical_data" / "processed"
        source_root = root / "ml" / "datasets" / "historical_disasters" / "EM-DAT"
        workbooks = sorted(source_root.glob("*.xlsx"))
        if not workbooks:
            return {
                "status": "NOT_READY",
                "analytics_status": "UNAVAILABLE",
                "training_status": "NOT_READY",
                "source_status": "UNAVAILABLE",
                "message": "No authorized source EM-DAT workbook is present.",
                "validated_event_datasets": [],
            }

        event_datasets: list[dict[str, Any]] = []
        for manifest_path in sorted(datasets_root.glob("*.manifest.json")):
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                dataset_path = manifest_path.with_suffix("").with_suffix(".csv")
                content_hash = sha256_file(dataset_path, normalize_csv_line_endings=True)
                with dataset_path.open(encoding="utf-8") as dataset_file:
                    row_count = max(0, sum(1 for _ in dataset_file) - 1)
                validation_errors = []
                source_name = manifest.get("source_file")
                if source_name:
                    source_path = source_root / Path(str(source_name)).name
                    if (
                        Path(str(source_name)).name != str(source_name)
                        or not source_path.is_file()
                        or _sha256(source_path) != manifest.get("source_sha256")
                    ):
                        validation_errors.append("Source workbook is missing or its hash does not match.")
                input_name = manifest.get("processed_input_file")
                if input_name:
                    input_path = datasets_root / Path(str(input_name)).name
                    if (
                        Path(str(input_name)).name != str(input_name)
                        or not input_path.is_file()
                        or _sha256(input_path) != manifest.get("processed_input_sha256")
                    ):
                        validation_errors.append("Processed input is missing or its hash does not match.")
                if manifest.get("dataset_sha256") != content_hash:
                    validation_errors.append("Dataset SHA-256 does not match its manifest.")
                if manifest.get("validation", {}).get("sha256") != content_hash:
                    validation_errors.append("Validation SHA-256 does not match the dataset.")
                if manifest.get("validation", {}).get("non_empty") is not True or row_count == 0:
                    validation_errors.append("Dataset is empty or marked empty.")
                if manifest.get("row_count") != row_count:
                    validation_errors.append("Dataset row count does not match its manifest.")
                passed = not validation_errors
                event_datasets.append(
                    {
                        "name": manifest.get("dataset_name", manifest_path.stem),
                        "path": str(dataset_path.relative_to(project_root)),
                        "manifest": str(manifest_path.relative_to(project_root)),
                        "status": "VALIDATED" if passed else "ERROR",
                        "rows": row_count,
                        "sha256": content_hash,
                        "error": "; ".join(validation_errors) if validation_errors else None,
                    }
                )
            except (OSError, ValueError, TypeError, AttributeError, json.JSONDecodeError) as error:
                event_datasets.append(
                    {
                        "name": manifest_path.stem,
                        "path": None,
                        "manifest": str(manifest_path.relative_to(project_root)),
                        "status": "ERROR",
                        "rows": None,
                        "error": str(error),
                    }
                )

        validated_count = sum(dataset["status"] == "VALIDATED" for dataset in event_datasets)
        analytics: dict[str, Any] | None = None
        analytics_error: str | None = None
        if event_datasets and validated_count == len(event_datasets):
            try:
                analytics = get_historical_analytics(root)
            except (OSError, ValueError) as error:
                analytics_error = str(error)
        analytics_status = (
            "READY"
            if analytics is not None
            else "ERROR"
            if analytics_error
            else "NOT_READY"
        )
        return {
            "status": "READY" if analytics_status == "READY" else "NOT_READY",
            "analytics_status": analytics_status,
            "training_status": "NOT_READY",
            "source_status": "VALIDATED" if validated_count else "UNVALIDATED",
            "message": analytics_error or (
                f"{validated_count} historical event datasets passed manifest validation and are usable for "
                "descriptive analytics. They do not provide validated flood-prediction labels or aligned "
                "environmental predictors; supervised flood training remains blocked."
                if analytics_status == "READY"
                else "Historical analytics require all dataset manifests and source hashes to validate."
            ),
            "analytics_summary": (
                {
                    "source_rows_across_extracts": analytics["summary"]["source_rows_across_extracts"],
                    "unique_event_ids": analytics["summary"]["unique_event_ids"],
                    "flood_events": analytics["summary"]["events_by_disaster_type"].get("Flood", 0),
                    "dataset_count": len(analytics["dataset_inventory"]),
                }
                if analytics is not None
                else None
            ),
            "analytics_error": analytics_error,
            "source_workbook": str(workbooks[0].relative_to(project_root)),
            "validated_event_datasets": event_datasets,
            "training_blockers": [
                "No verified site-level flood target definition or continuous training label.",
                "No spatially and temporally joined historical weather/hydrology observations.",
                "The legacy 20-feature indices have no verified units, sources, or transformations.",
                "No evidence that the event-level records represent non-event conditions at monitored locations.",
            ],
        }

    return _get_cached_value(cache_key, build_result)


def get_historical_analytics(project_root: Path = PROJECT_ROOT) -> dict[str, Any]:
    """Return validated descriptive aggregates without changing or exposing source rows."""
    root = Path(project_root).resolve()
    cache_key = ("historical_analytics", str(root), _dataset_fingerprint(root))
    return _get_cached_value(cache_key, lambda: build_historical_analytics(root))
