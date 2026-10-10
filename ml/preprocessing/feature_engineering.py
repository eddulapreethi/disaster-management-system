from collections.abc import Sequence

import numpy as np
import pandas as pd

FLOOD_FEATURES: tuple[str, ...] = (
    "MonsoonIntensity",
    "TopographyDrainage",
    "RiverManagement",
    "Deforestation",
    "Urbanization",
    "ClimateChange",
    "DamsQuality",
    "Siltation",
    "AgriculturalPractices",
    "Encroachments",
    "IneffectiveDisasterPreparedness",
    "DrainageSystems",
    "CoastalVulnerability",
    "Landslides",
    "Watersheds",
    "DeterioratingInfrastructure",
    "PopulationScore",
    "WetlandLoss",
    "InadequatePlanning",
    "PoliticalFactors",
)

FLOOD_FEATURE_SCHEMA_VERSION = "flood-risk-factors-v1"
FLOOD_FEATURE_RANGE = (0.0, 16.0)
FLOOD_FEATURE_SCHEMA: tuple[dict[str, str | float], ...] = tuple(
    {
        "name": name,
        "meaning": name,
        "data_type": "numeric",
        "unit": "unverified 0-16 index; no authoritative data dictionary is present",
        "minimum": FLOOD_FEATURE_RANGE[0],
        "maximum": FLOOD_FEATURE_RANGE[1],
        "missing_values": "not accepted at inference; training data must be explicitly cleaned",
        "source": "not documented in the repository; requires a cited, location/time-aligned source",
        "transformation": "none documented",
    }
    for name in FLOOD_FEATURES
)


def select_features(frame: pd.DataFrame, feature_names: Sequence[str] = FLOOD_FEATURES) -> pd.DataFrame:
    """Return model features in canonical order, rejecting missing columns."""
    missing = [name for name in feature_names if name not in frame.columns]
    if missing:
        raise ValueError(f"Dataset is missing required feature columns: {', '.join(missing)}")
    selected = frame.loc[:, list(feature_names)].copy()
    for name in feature_names:
        try:
            selected[name] = pd.to_numeric(selected[name], errors="raise")
        except (TypeError, ValueError) as error:
            raise ValueError(f"Feature {name!r} must contain numeric values.") from error
        if selected[name].isna().any():
            raise ValueError(f"Feature {name!r} contains missing values.")
        values = selected[name].to_numpy(dtype=float)
        if not np.isfinite(values).all():
            raise ValueError(f"Feature {name!r} contains non-finite values.")
        if ((values < FLOOD_FEATURE_RANGE[0]) | (values > FLOOD_FEATURE_RANGE[1])).any():
            raise ValueError(f"Feature {name!r} must be between 0 and 16.")
    return selected
