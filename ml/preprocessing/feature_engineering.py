from collections.abc import Sequence

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


def select_features(frame: pd.DataFrame, feature_names: Sequence[str] = FLOOD_FEATURES) -> pd.DataFrame:
    """Return model features in canonical order, rejecting missing columns."""
    missing = [name for name in feature_names if name not in frame.columns]
    if missing:
        raise ValueError(f"Dataset is missing required feature columns: {', '.join(missing)}")
    return frame.loc[:, list(feature_names)].copy()
