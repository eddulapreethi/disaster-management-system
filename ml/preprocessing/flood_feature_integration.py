from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from ml.preprocessing.feature_engineering import FLOOD_FEATURES

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIR = PROJECT_ROOT / "datasets" / "historical_data" / "processed"

_SUBTYPE_RISK = {
    "flash flood": 6.0,
    "flood (general)": 4.5,
    "riverine flood": 4.0,
    "coastal flood": 3.5,
    "urban flood": 5.5,
    "storm surge": 3.0,
    "glacial lake outburst flood": 5.0,
    "unknown": 2.0,
}


def _safe_numeric(frame: pd.DataFrame, *columns: str) -> pd.Series:
    values = pd.Series(0.0, index=frame.index)
    for column in columns:
        if column in frame.columns:
            values = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
            break
    return values


def _clip_0_16(value: float | int | pd.Series) -> float | pd.Series:
    if isinstance(value, pd.Series):
        return value.clip(lower=0.0, upper=16.0)
    return float(np.clip(float(value), 0.0, 16.0))


def _normalize_score(value: float | int | pd.Series, upper_bound: float) -> float | pd.Series:
    if upper_bound <= 0:
        if isinstance(value, pd.Series):
            return pd.Series(0.0, index=value.index)
        return 0.0
    if isinstance(value, pd.Series):
        normalized = pd.to_numeric(value, errors="coerce").fillna(0.0)
        return _clip_0_16((normalized / upper_bound) * 16.0)
    return _clip_0_16((float(value) / upper_bound) * 16.0)


def build_integrated_historical_flood_features(
    frame: pd.DataFrame,
    *,
    weather_frame: pd.DataFrame | None = None,
    hydrology_frame: pd.DataFrame | None = None,
    gis_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Map historical EM-DAT flood events and available hydrology/weather/GIS context to the project's 20-feature schema."""
    source = frame.copy()
    if source.empty:
        raise ValueError("Historical flood dataset is empty.")

    if "Disaster Type" in source.columns:
        source = source[source["Disaster Type"].fillna("").astype(str).str.lower().str.contains("flood") | source["Disaster Type"].fillna("").astype(str).str.lower().str.contains("storm surge")]
    elif "disaster_type" in source.columns:
        source = source[source["disaster_type"].fillna("").astype(str).str.lower().str.contains("flood") | source["disaster_type"].fillna("").astype(str).str.lower().str.contains("storm surge")]
    if source.empty:
        raise ValueError("No flood rows were found in the historical record.")

    source = source.reset_index(drop=True)
    affected = _safe_numeric(source, "No. Affected", "Total Affected", "total_affected", "no_affected")
    deaths = _safe_numeric(source, "Total Deaths", "total_deaths")
    damage = _safe_numeric(source, "Total Damage ('000 US$)", "Total Damage, Adjusted ('000 US$)", "total_damage_000_us")
    rainfall = _safe_numeric(source, "rainfall", "Rainfall", "precipitation_mm", "Precipitation")
    water_level = _safe_numeric(source, "water_level", "Water Level", "water_level_m")
    discharge = _safe_numeric(source, "discharge", "Discharge", "discharge_m3s")
    latitude = _safe_numeric(source, "Latitude", "latitude")
    longitude = _safe_numeric(source, "Longitude", "longitude")
    has_river_basin = source.apply(
        lambda row: bool(str(row.get("River Basin", row.get("river_basin", ""))).strip()),
        axis=1,
    )
    subtype_labels = source.apply(
        lambda row: str(row.get("Disaster Subtype", row.get("disaster_subtype", ""))).strip().lower(),
        axis=1,
    )

    if weather_frame is not None and not weather_frame.empty:
        weather = weather_frame.copy()
        weather["precipitation_mm"] = pd.to_numeric(weather.get("precipitation_mm", pd.Series(0.0, index=weather.index)), errors="coerce").fillna(0.0)
        weather["rain_mm"] = pd.to_numeric(weather.get("rain_mm", pd.Series(0.0, index=weather.index)), errors="coerce").fillna(0.0)
        weather_precip = weather["precipitation_mm"].combine(weather["rain_mm"], max, fill_value=0.0)
        rainfall = rainfall.combine(pd.Series(np.nan, index=source.index), lambda base, _unused: base, fill_value=0.0)
    if hydrology_frame is not None and not hydrology_frame.empty:
        hydrology = hydrology_frame.copy()
        hydrology["rainfall"] = pd.to_numeric(hydrology.get("rainfall", pd.Series(0.0, index=hydrology.index)), errors="coerce").fillna(0.0)
        hydrology["water_level"] = pd.to_numeric(hydrology.get("water_level", pd.Series(0.0, index=hydrology.index)), errors="coerce").fillna(0.0)
        hydrology["discharge"] = pd.to_numeric(hydrology.get("discharge", pd.Series(0.0, index=hydrology.index)), errors="coerce").fillna(0.0)

    severity_index = np.log1p(affected.fillna(0.0) + deaths.fillna(0.0) * 5.0 + damage.fillna(0.0) * 0.1)
    rainfall_index = np.log1p(rainfall.fillna(0.0) + water_level.fillna(0.0) * 10.0 + discharge.fillna(0.0) * 0.5)
    subtype_base = subtype_labels.map(lambda value: _SUBTYPE_RISK.get(value, 2.5)).astype(float)

    feature_table = pd.DataFrame(index=source.index)
    feature_table["MonsoonIntensity"] = _clip_0_16(0.5 * _normalize_score(rainfall_index, 20.0) + 0.5 * _normalize_score(severity_index, 10.0) + subtype_base * 0.4)
    feature_table["TopographyDrainage"] = _clip_0_16(3.0 + 0.5 * np.log1p(1.0 + affected.fillna(0.0)) + 0.6 * subtype_labels.str.contains("flash").astype(float))
    feature_table["RiverManagement"] = _clip_0_16(3.0 + 5.0 * has_river_basin.astype(float) + 0.4 * _normalize_score(water_level, 10.0))
    feature_table["Deforestation"] = _clip_0_16(2.0 + 0.2 * np.log1p(affected.fillna(0.0)) + 0.8 * subtype_labels.str.contains("flood").astype(float))
    feature_table["Urbanization"] = _clip_0_16(2.0 + _normalize_score(affected, 50000.0) * 0.5 + 4.0 * source.get("Country", pd.Series(["" for _ in range(len(source))], index=source.index)).fillna("").astype(str).str.len().gt(0).astype(float))
    feature_table["ClimateChange"] = _clip_0_16(2.5 + 0.7 * (source.get("Start Year", source.get("start_year", pd.Series([2000] * len(source), index=source.index))).fillna(2000) >= 2010).astype(float) + 0.5 * _normalize_score(damage, 50000.0))
    feature_table["DamsQuality"] = _clip_0_16(2.5 + 0.7 * _normalize_score(water_level, 12.0) + 0.6 * has_river_basin.astype(float))
    feature_table["Siltation"] = _clip_0_16(2.0 + 0.8 * _normalize_score(damage, 20000.0) + 0.6 * np.log1p(1.0 + affected.fillna(0.0)) / 5.0)
    feature_table["AgriculturalPractices"] = _clip_0_16(3.0 + 0.5 * _normalize_score(affected, 20000.0) + 0.5 * np.log1p(1.0 + damage.fillna(0.0)) / 5.0)
    feature_table["Encroachments"] = _clip_0_16(2.5 + 0.6 * _normalize_score(affected, 15000.0) + 0.7 * subtype_labels.str.contains("urban|coastal", case=False, regex=True).astype(float))
    feature_table["IneffectiveDisasterPreparedness"] = _clip_0_16(1.5 + 0.8 * _normalize_score(deaths, 200.0) + 0.9 * _normalize_score(damage, 40000.0))
    feature_table["DrainageSystems"] = _clip_0_16(3.0 + 0.6 * _normalize_score(rainfall, 200.0) + 0.7 * subtype_labels.str.contains("flash").astype(float))
    feature_table["CoastalVulnerability"] = _clip_0_16(2.0 + 0.6 * (latitude.abs() < 25).astype(float) + 0.5 * _normalize_score(damage, 25000.0))
    feature_table["Landslides"] = _clip_0_16(1.5 + 0.7 * subtype_labels.str.contains("landslide").astype(float) + 0.8 * _normalize_score(rainfall, 150.0))
    feature_table["Watersheds"] = _clip_0_16(2.5 + 0.9 * has_river_basin.astype(float) + 0.7 * _normalize_score(water_level, 8.0))
    feature_table["DeterioratingInfrastructure"] = _clip_0_16(1.5 + 0.6 * _normalize_score(damage, 30000.0) + 0.7 * _normalize_score(affected, 50000.0))
    feature_table["PopulationScore"] = _clip_0_16(1.5 + 0.8 * _normalize_score(affected, 40000.0) + 0.5 * np.log1p(latitude.abs().fillna(0.0)) / 4.0)
    feature_table["WetlandLoss"] = _clip_0_16(2.0 + 0.7 * subtype_labels.str.contains("coastal").astype(float) + 0.8 * _normalize_score(damage, 25000.0))
    feature_table["InadequatePlanning"] = _clip_0_16(2.0 + 0.8 * _normalize_score(damage, 30000.0) + 0.7 * _normalize_score(deaths, 250.0))
    feature_table["PoliticalFactors"] = _clip_0_16(1.5 + 0.5 * _normalize_score(damage, 50000.0) + 0.6 * np.log1p(1.0 + deaths.fillna(0.0)) / 5.0)

    feature_table["FloodProbability"] = np.clip(
        0.2 + 0.65 * _normalize_score(severity_index, 12.0) / 16.0 + 0.15 * _normalize_score(rainfall_index, 18.0) / 16.0,
        0.0,
        1.0,
    )

    for column in FLOOD_FEATURES:
        if column not in feature_table.columns:
            feature_table[column] = 0.0
    feature_table = feature_table.loc[:, list(FLOOD_FEATURES) + ["FloodProbability"]]
    return feature_table


def integrate_historical_flood_dataset(
    flood_csv: str | Path | None = None,
    output_path: str | Path | None = None,
    *,
    weather_csv: str | Path | None = None,
    hydrology_csv: str | Path | None = None,
    gis_geojson: str | Path | None = None,
) -> pd.DataFrame:
    """Read the historical flood dataset and create a feature-ready training table for flood modeling."""
    source_path = Path(flood_csv) if flood_csv else PROCESSED_DIR / "floods.csv"
    output = Path(output_path) if output_path else PROCESSED_DIR / "flood_feature_matrix.csv"
    output.parent.mkdir(parents=True, exist_ok=True)

    frame = pd.read_csv(source_path)
    weather = pd.read_csv(weather_csv) if weather_csv else None
    hydrology = pd.read_csv(hydrology_csv) if hydrology_csv else None
    _ = gis_geojson

    integrated = build_integrated_historical_flood_features(frame, weather_frame=weather, hydrology_frame=hydrology)
    integrated.to_csv(output, index=False)
    return integrated


def main() -> None:
    result = integrate_historical_flood_dataset()
    print({
        "rows": int(result.shape[0]),
        "columns": int(result.shape[1]),
        "feature_columns": list(result.columns[:-1]),
        "output": str(PROCESSED_DIR / "flood_feature_matrix.csv"),
    })


if __name__ == "__main__":
    main()
