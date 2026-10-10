import json
from pathlib import Path
from typing import Any

from ml.preprocessing.feature_engineering import (
    FLOOD_FEATURES,
    FLOOD_FEATURE_SCHEMA_VERSION,
)

MANIFEST_REQUIRED_FIELDS = (
    "dataset_name",
    "dataset_version",
    "source_name",
    "source_reference",
    "license",
    "geographic_coverage",
    "temporal_coverage",
    "spatiotemporal_linkage",
    "row_definition",
    "grouping_policy",
    "target_definition",
    "target_interpretation",
    "feature_schema_version",
    "feature_definitions",
)
FEATURE_REQUIRED_FIELDS = (
    "meaning",
    "data_type",
    "unit",
    "minimum",
    "maximum",
    "source",
    "transformation",
)
UNVERIFIED_VALUES = {
    "",
    "unknown",
    "n/a",
    "na",
    "not documented",
    "tbd",
    "todo",
    "placeholder",
    "verified definition",
    "documented unit",
    "source field and source reference",
    "reproducible conversion",
}


def _is_unverified(value: Any) -> bool:
    normalized = str(value).strip().casefold()
    return normalized in UNVERIFIED_VALUES or normalized.startswith(("todo:", "placeholder:"))


def validate_dataset_manifest(manifest: Any) -> dict[str, Any]:
    """Validate the declared provenance and definitions required for model training."""
    if not isinstance(manifest, dict):
        raise ValueError("Dataset manifest must be a JSON object.")

    missing = [name for name in MANIFEST_REQUIRED_FIELDS if not manifest.get(name)]
    if missing:
        raise ValueError(f"Dataset manifest is missing required fields: {', '.join(missing)}")
    for field in MANIFEST_REQUIRED_FIELDS:
        if field == "feature_definitions":
            continue
        if _is_unverified(manifest[field]):
            raise ValueError(f"Dataset manifest field {field!r} must contain a concrete definition.")
    if manifest["feature_schema_version"] != FLOOD_FEATURE_SCHEMA_VERSION:
        raise ValueError(
            f"Dataset manifest feature_schema_version must be {FLOOD_FEATURE_SCHEMA_VERSION!r}."
        )
    if manifest["target_interpretation"] != "continuous_index":
        raise ValueError(
            "This regressor supports a continuous_index target only. Probability targets require "
            "a separately validated calibration pipeline."
        )

    definitions = manifest["feature_definitions"]
    if not isinstance(definitions, dict):
        raise ValueError("Dataset manifest feature_definitions must be a JSON object.")
    if set(definitions) != set(FLOOD_FEATURES):
        missing_features = sorted(set(FLOOD_FEATURES) - set(definitions))
        extra_features = sorted(set(definitions) - set(FLOOD_FEATURES))
        details = []
        if missing_features:
            details.append(f"missing: {', '.join(missing_features)}")
        if extra_features:
            details.append(f"unexpected: {', '.join(extra_features)}")
        raise ValueError("Dataset manifest feature definitions do not match the canonical schema (" + "; ".join(details) + ").")

    for name in FLOOD_FEATURES:
        definition = definitions[name]
        if not isinstance(definition, dict):
            raise ValueError(f"Dataset manifest definition for {name!r} must be an object.")
        missing_fields = [
            field
            for field in FEATURE_REQUIRED_FIELDS
            if field not in definition
            or definition[field] is None
            or (isinstance(definition[field], str) and not definition[field].strip())
        ]
        if missing_fields:
            raise ValueError(
                f"Dataset manifest definition for {name!r} is missing: {', '.join(missing_fields)}."
            )
        for field in FEATURE_REQUIRED_FIELDS:
            if _is_unverified(definition[field]):
                raise ValueError(
                    f"Dataset manifest definition for {name!r} must provide a verified {field}."
                )
        if definition["data_type"] != "numeric":
            raise ValueError(f"Dataset manifest definition for {name!r} must use numeric values.")
        if (
            isinstance(definition["minimum"], bool)
            or isinstance(definition["maximum"], bool)
            or definition["minimum"] != 0
            or definition["maximum"] != 16
        ):
            raise ValueError(
                f"Dataset manifest definition for {name!r} must declare the canonical numeric range 0 to 16."
            )
        unit = str(definition["unit"]).casefold()
        if "index" not in unit and "ordinal" not in unit:
            raise ValueError(
                f"Dataset manifest definition for {name!r} must document the dimensionless 0-16 index unit."
            )
    return manifest


def load_dataset_manifest(manifest_path: str | Path) -> dict[str, Any]:
    path = Path(manifest_path)
    try:
        with path.open(encoding="utf-8") as manifest_file:
            manifest = json.load(manifest_file)
    except FileNotFoundError as error:
        raise ValueError(
            f"Training requires a provenance manifest at {path}. See ml/README.md for the required format."
        ) from error
    except json.JSONDecodeError as error:
        raise ValueError(f"Dataset manifest {path} is not valid JSON.") from error
    return validate_dataset_manifest(manifest)


def default_manifest_path(dataset_path: str | Path) -> Path:
    dataset = Path(dataset_path)
    return dataset.with_name(f"{dataset.stem}.manifest.json")
