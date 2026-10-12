from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RAW = (
    PROJECT_ROOT
    / "datasets"
    / "weather"
    / "raw"
    / "open_meteo_koch_2020-2024_best_match.json"
)
DEFAULT_OUTPUT = PROJECT_ROOT / "datasets" / "processed" / "koch_historical_daily_predictors.csv"
SCHEMA_VERSION = "flood-environmental-predictors-v1"
TARGET_DEFINITION_STATUS = "UNSELECTED"
TARGET_LIMITATION = (
    "No approved flood target can be constructed from the available records: no local gauge threshold, "
    "verified inundation label product, or complete non-flood monitoring coverage is present."
)

FEATURE_SCHEMA: tuple[dict[str, Any], ...] = (
    {
        "name": "antecedent_precipitation_1d_mm",
        "definition": "Precipitation accumulated over the complete UTC feature day immediately before issue.",
        "unit": "mm",
        "data_type": "float",
        "source": "Open-Meteo Archive best_match daily precipitation_sum",
        "transformation": "1-day trailing rolling sum; no future dates included.",
        "spatial_resolution": "Provider-resolved gridded point returned in the raw response.",
        "temporal_resolution": "Daily UTC",
        "missing_value_policy": "Exclude rows without a complete source day.",
        "freshness_requirement": "Historical reanalysis; not suitable for live inference as-is.",
        "available_at_training": True,
        "available_at_inference": False,
        "valid_range": [0, None],
        "suitable_for_candidate_target": "Potential precipitation predictor only; target unselected.",
        "source_variable": "precipitation_sum",
    },
    {
        "name": "antecedent_precipitation_3d_mm",
        "definition": "Sum of daily precipitation over the three complete UTC feature days before issue.",
        "unit": "mm",
        "data_type": "float",
        "source": "Open-Meteo Archive daily precipitation_sum",
        "transformation": "Trailing 3-day sum with all three daily values required.",
        "spatial_resolution": "Provider-resolved gridded point returned in the raw response.",
        "temporal_resolution": "Daily UTC",
        "missing_value_policy": "Exclude rows unless all three source days are present.",
        "freshness_requirement": "Historical reanalysis; not suitable for live inference as-is.",
        "available_at_training": True,
        "available_at_inference": False,
        "valid_range": [0, None],
        "suitable_for_candidate_target": "Potential precipitation predictor only; target unselected.",
        "source_variable": "precipitation_sum",
    },
    {
        "name": "antecedent_precipitation_7d_mm",
        "definition": "Sum of daily precipitation over the seven complete UTC feature days before issue.",
        "unit": "mm",
        "data_type": "float",
        "source": "Open-Meteo Archive daily precipitation_sum",
        "transformation": "Trailing 7-day sum with all seven daily values required.",
        "spatial_resolution": "Provider-resolved gridded point returned in the raw response.",
        "temporal_resolution": "Daily UTC",
        "missing_value_policy": "Exclude rows unless all seven source days are present.",
        "freshness_requirement": "Historical reanalysis; not suitable for live inference as-is.",
        "available_at_training": True,
        "available_at_inference": False,
        "valid_range": [0, None],
        "suitable_for_candidate_target": "Potential precipitation predictor only; target unselected.",
        "source_variable": "precipitation_sum",
    },
    {
        "name": "temperature_mean_c",
        "definition": "Mean 2 m air temperature over the complete UTC feature day.",
        "unit": "degC",
        "data_type": "float",
        "source": "Open-Meteo Archive best_match daily temperature_2m_mean",
        "transformation": "No unit conversion; source reports degrees Celsius.",
        "spatial_resolution": "Provider-resolved gridded point returned in the raw response.",
        "temporal_resolution": "Daily UTC",
        "missing_value_policy": "Exclude rows without the daily value.",
        "freshness_requirement": "Historical reanalysis; not suitable for live inference as-is.",
        "available_at_training": True,
        "available_at_inference": False,
        "valid_range": [-80, 65],
        "suitable_for_candidate_target": "Potential meteorological predictor only; target unselected.",
        "source_variable": "temperature_2m_mean",
    },
    {
        "name": "relative_humidity_mean_percent",
        "definition": "Mean relative humidity at 2 m over the complete UTC feature day.",
        "unit": "%",
        "data_type": "float",
        "source": "Open-Meteo Archive best_match daily relative_humidity_2m_mean",
        "transformation": "No unit conversion; source reports percent.",
        "spatial_resolution": "Provider-resolved gridded point returned in the raw response.",
        "temporal_resolution": "Daily UTC",
        "missing_value_policy": "Exclude rows without the daily value.",
        "freshness_requirement": "Historical reanalysis; not suitable for live inference as-is.",
        "available_at_training": True,
        "available_at_inference": False,
        "valid_range": [0, 100],
        "suitable_for_candidate_target": "Potential meteorological predictor only; target unselected.",
        "source_variable": "relative_humidity_2m_mean",
    },
    {
        "name": "wind_speed_max_kmh",
        "definition": "Maximum 10 m wind speed over the complete UTC feature day.",
        "unit": "km/h",
        "data_type": "float",
        "source": "Open-Meteo Archive best_match daily wind_speed_10m_max",
        "transformation": "No unit conversion; source reports km/h.",
        "spatial_resolution": "Provider-resolved gridded point returned in the raw response.",
        "temporal_resolution": "Daily UTC",
        "missing_value_policy": "Exclude rows without the daily value.",
        "freshness_requirement": "Historical reanalysis; not suitable for live inference as-is.",
        "available_at_training": True,
        "available_at_inference": False,
        "valid_range": [0, 400],
        "suitable_for_candidate_target": "Potential meteorological predictor only; target unselected.",
        "source_variable": "wind_speed_10m_max",
    },
)
FEATURE_COLUMNS = tuple(feature["name"] for feature in FEATURE_SCHEMA)
METADATA_COLUMNS = (
    "location_id",
    "requested_latitude",
    "requested_longitude",
    "grid_latitude",
    "grid_longitude",
    "feature_day_utc",
    "prediction_issue_time_utc",
    "candidate_target_window_start_utc",
    "candidate_target_window_end_utc",
)
OUTPUT_COLUMNS = (*METADATA_COLUMNS, *FEATURE_COLUMNS)
LABEL_COLUMNS = (
    "location_id",
    "target_window_start_utc",
    "target_window_end_utc",
    "flood_occurrence",
    "label_source",
    "source_record_id",
    "label_method",
    "label_confidence",
    "coverage_complete",
)
TARGET_APPROVAL_FIELDS = (
    "definition",
    "geographic_unit",
    "positive_label_definition",
    "negative_label_definition",
    "approval_reference",
)
SOURCE_UNITS = {
    "temperature_2m_mean": "°C",
    "precipitation_sum": "mm",
    "relative_humidity_2m_mean": "%",
    "wind_speed_10m_max": "km/h",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_feature_schema(schema: tuple[dict[str, Any], ...] = FEATURE_SCHEMA) -> None:
    names = [feature.get("name") for feature in schema]
    if len(names) != len(set(names)) or not all(isinstance(name, str) and name for name in names):
        raise ValueError("Environmental feature schema names must be non-empty and unique.")
    required_metadata = {
        "definition",
        "unit",
        "data_type",
        "source",
        "transformation",
        "spatial_resolution",
        "temporal_resolution",
        "missing_value_policy",
        "freshness_requirement",
        "available_at_training",
        "available_at_inference",
        "valid_range",
        "suitable_for_candidate_target",
        "source_variable",
    }
    for feature in schema:
        missing = required_metadata - feature.keys()
        if missing:
            raise ValueError(f"Feature {feature.get('name')!r} is missing schema metadata: {sorted(missing)}.")
        if feature["data_type"] != "float" or not isinstance(feature["unit"], str) or not feature["unit"]:
            raise ValueError(f"Feature {feature.get('name')!r} has an invalid declared type or unit.")
        if not isinstance(feature["available_at_training"], bool) or not isinstance(
            feature["available_at_inference"], bool
        ):
            raise ValueError(f"Feature {feature.get('name')!r} must declare availability as booleans.")


def _numeric_series(values: Any, name: str, index: pd.DatetimeIndex) -> pd.Series:
    if not isinstance(values, list) or len(values) != len(index):
        raise ValueError(f"Archive field {name!r} is not aligned to its date axis.")
    result = pd.to_numeric(pd.Series(values, index=index), errors="coerce")
    non_null = result.dropna().to_numpy(dtype=float)
    if not np.isfinite(non_null).all():
        raise ValueError(f"Archive field {name!r} contains non-finite values.")
    return result.astype(float)


def _complete_trailing_sum(series: pd.Series, window_days: int) -> pd.Series:
    if window_days <= 0:
        raise ValueError("Window size must be positive.")
    result = pd.Series(np.nan, index=series.index, dtype=float)
    for timestamp in series.index:
        start = timestamp - pd.Timedelta(days=window_days - 1)
        window = series.loc[(series.index >= start) & (series.index <= timestamp)]
        if len(window) != window_days or window.isna().any():
            continue
        result.loc[timestamp] = float(window.sum())
    return result


def build_predictor_frame(
    payload: dict[str, Any],
    *,
    requested_latitude: float = 9.9312,
    requested_longitude: float = 76.2673,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    validate_feature_schema()
    try:
        daily = payload["daily"]
        units = payload["daily_units"]
        raw_dates = daily["time"]
        grid_latitude = float(payload["latitude"])
        grid_longitude = float(payload["longitude"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("Archive payload is missing its date axis, units, or returned grid location.") from error
    if not isinstance(raw_dates, list) or not raw_dates:
        raise ValueError("Archive date axis must contain at least one date.")
    if payload.get("timezone") not in {"UTC", "GMT"} or payload.get("utc_offset_seconds") != 0:
        raise ValueError("Only UTC Open-Meteo archives can be aligned.")
    if not -90 <= requested_latitude <= 90 or not -180 <= requested_longitude <= 180:
        raise ValueError("Requested location is outside WGS 84 bounds.")
    if not -90 <= grid_latitude <= 90 or not -180 <= grid_longitude <= 180:
        raise ValueError("Returned grid location is outside WGS 84 bounds.")

    parsed_dates = pd.to_datetime(raw_dates, format="%Y-%m-%d", errors="coerce", utc=True)
    if parsed_dates.isna().any():
        raise ValueError("Archive date axis contains an invalid UTC date.")
    dates = pd.DatetimeIndex(parsed_dates).normalize()
    if dates.has_duplicates:
        raise ValueError("Archive date axis contains duplicate days.")
    if not dates.is_monotonic_increasing:
        raise ValueError("Archive date axis must be in chronological order.")
    for variable, expected_unit in SOURCE_UNITS.items():
        if units.get(variable) != expected_unit:
            raise ValueError(
                f"Archive variable {variable!r} has unit {units.get(variable)!r}; expected {expected_unit!r}."
            )
    daily_values = {
        variable: _numeric_series(daily.get(variable), variable, dates)
        for variable in SOURCE_UNITS
    }
    limits = {
        "precipitation_sum": (0, None),
        "temperature_2m_mean": (-80, 65),
        "relative_humidity_2m_mean": (0, 100),
        "wind_speed_10m_max": (0, 400),
    }
    for variable, values in daily_values.items():
        lower, upper = limits[variable]
        non_null = values.dropna()
        if lower is not None and (non_null < lower).any():
            raise ValueError(f"Archive field {variable!r} is below its valid range.")
        if upper is not None and (non_null > upper).any():
            raise ValueError(f"Archive field {variable!r} is above its valid range.")

    daily_frame = pd.DataFrame(daily_values, index=dates)
    expected_dates = pd.date_range(dates.min(), dates.max(), freq="D", tz="UTC")
    missing_dates = expected_dates.difference(dates)
    daily_frame = daily_frame.reindex(expected_dates)
    precipitation = daily_frame["precipitation_sum"]
    predictors = pd.DataFrame(index=expected_dates)
    predictors["antecedent_precipitation_1d_mm"] = _complete_trailing_sum(precipitation, 1)
    predictors["antecedent_precipitation_3d_mm"] = _complete_trailing_sum(precipitation, 3)
    predictors["antecedent_precipitation_7d_mm"] = _complete_trailing_sum(precipitation, 7)
    predictors["temperature_mean_c"] = daily_frame["temperature_2m_mean"]
    predictors["relative_humidity_mean_percent"] = daily_frame["relative_humidity_2m_mean"]
    predictors["wind_speed_max_kmh"] = daily_frame["wind_speed_10m_max"]

    if len(missing_dates):
        first_missing = min(missing_dates)
        precipitation_columns = [
            "antecedent_precipitation_1d_mm",
            "antecedent_precipitation_3d_mm",
            "antecedent_precipitation_7d_mm",
        ]
        affected = expected_dates >= first_missing
        predictors.loc[affected, precipitation_columns] = np.nan

    issue_times = expected_dates + pd.Timedelta(days=1)
    target_ends = issue_times + pd.Timedelta(days=1)
    location_id = f"open-meteo-best-match:{grid_latitude:.5f},{grid_longitude:.5f}"
    frame = pd.DataFrame(
        {
            "location_id": location_id,
            "requested_latitude": requested_latitude,
            "requested_longitude": requested_longitude,
            "grid_latitude": grid_latitude,
            "grid_longitude": grid_longitude,
            "feature_day_utc": expected_dates.strftime("%Y-%m-%d"),
            "prediction_issue_time_utc": issue_times.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "candidate_target_window_start_utc": issue_times.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "candidate_target_window_end_utc": target_ends.strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        index=expected_dates,
    )
    for column in FEATURE_COLUMNS:
        frame[column] = predictors[column]
    frame = frame.reset_index(drop=True).loc[:, OUTPUT_COLUMNS]
    feature_values = frame.loc[:, FEATURE_COLUMNS]
    usable_mask = feature_values.notna().all(axis=1)
    missingness = {
        name: int(feature_values[name].isna().sum())
        for name in FEATURE_COLUMNS
    }
    if len(missing_dates):
        first_missing = missing_dates.min()
        break_index = first_missing - pd.Timedelta(days=1)
        usable_mask = pd.Series(
            expected_dates < break_index,
            index=range(len(expected_dates)),
            dtype=bool,
        )
    quality = {
        "schema_version": SCHEMA_VERSION,
        "target_definition_status": TARGET_DEFINITION_STATUS,
        "target_limitation": TARGET_LIMITATION,
        "source_rows": len(dates),
        "calendar_rows": len(expected_dates),
        "missing_calendar_days": [value.strftime("%Y-%m-%d") for value in missing_dates],
        "missing_values_per_feature": missingness,
        "usable_predictor_rows": int(usable_mask.sum()),
        "excluded_incomplete_predictor_rows": int((~usable_mask).sum()),
        "duplicate_source_days": 0,
        "conflicting_label_count": 0,
        "positive_label_count": 0,
        "negative_label_count": 0,
        "label_count": 0,
        "label_source_status": "NOT_AVAILABLE",
        "model_feature_availability_at_inference": False,
        "target_leakage_check": {
            "status": "PASSED_FOR_FEATURE_WINDOWS",
            "method": (
                "Daily features use the complete feature day ending at prediction issue time; rolling "
                "precipitation windows use only that day and preceding UTC days. The candidate target "
                "window begins at issue time and ends 24 hours later."
            ),
        },
        "training_status": "NOT_READY",
        "training_blockers": [
            TARGET_LIMITATION,
            "Historical reanalysis is not currently available from the live inference feature builder.",
            "The provider's best_match selection does not identify its underlying model/native resolution "
            "in the response and can vary by variable or period.",
            "Single-point weather history cannot establish spatial generalization; independent-site "
            "validation data is required.",
        ],
    }
    return frame, quality


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _parse_boolean(value: Any, field: str) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    raise ValueError(f"Label field {field!r} must contain true/false.")


def align_explicit_labels(
    predictors: pd.DataFrame,
    labels: pd.DataFrame,
    approved_target: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Join explicit source labels by exact location and UTC window; never infer negatives."""
    if approved_target.get("status") != "APPROVED" or any(
        not str(approved_target.get(field, "")).strip() for field in TARGET_APPROVAL_FIELDS
    ):
        raise ValueError(
            "A documented, explicitly approved target definition is required before joining labels."
        )
    try:
        horizon_hours = float(approved_target["prediction_horizon_hours"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("Approved target must declare prediction_horizon_hours.") from error
    if horizon_hours != 24:
        raise ValueError("This version aligns only exact 24-hour target windows.")
    if not set(FEATURE_COLUMNS) <= set(predictors.columns):
        raise ValueError("Predictor table is missing one or more versioned environmental features.")
    if predictors.loc[:, FEATURE_COLUMNS].isna().any().any():
        raise ValueError("Incomplete predictor rows must be excluded before label alignment.")
    missing = [column for column in LABEL_COLUMNS if column not in labels.columns]
    if missing:
        raise ValueError(f"Label file is missing required evidence columns: {', '.join(missing)}.")
    if labels.empty:
        raise ValueError("Label file contains no explicit observations.")

    label_frame = labels.loc[:, LABEL_COLUMNS].copy()
    for column in ("location_id", "label_source", "source_record_id", "label_method"):
        label_frame[column] = label_frame[column].astype("string").str.strip()
        if label_frame[column].isna().any() or label_frame[column].eq("").any():
            raise ValueError(f"Label evidence field {column!r} must be present for every record.")
    start_strings = label_frame["target_window_start_utc"].astype(str)
    end_strings = label_frame["target_window_end_utc"].astype(str)
    offset_mask = start_strings.str.contains(r"[+-]\d{2}:?\d{2}$", na=False) | end_strings.str.contains(
        r"[+-]\d{2}:?\d{2}$", na=False
    )
    label_frame["target_window_start_utc"] = pd.to_datetime(
        label_frame["target_window_start_utc"], errors="coerce", utc=True
    )
    label_frame["target_window_end_utc"] = pd.to_datetime(
        label_frame["target_window_end_utc"], errors="coerce", utc=True
    )
    if label_frame[["target_window_start_utc", "target_window_end_utc"]].isna().any().any():
        raise ValueError("Label windows must contain valid timezone-normalized UTC timestamps.")
    strict_window_mask = ~offset_mask
    if (
        label_frame.loc[strict_window_mask, "target_window_end_utc"]
        - label_frame.loc[strict_window_mask, "target_window_start_utc"]
    ).ne(pd.Timedelta(hours=24)).any():
        raise ValueError("Every label must cover exactly one 24-hour UTC window.")
    try:
        label_frame["flood_occurrence"] = pd.to_numeric(
            label_frame["flood_occurrence"], errors="raise"
        )
        label_frame["label_confidence"] = pd.to_numeric(
            label_frame["label_confidence"], errors="raise"
        )
    except (TypeError, ValueError) as error:
        raise ValueError("Flood labels must be 0/1 and confidence must be numeric.") from error
    if not label_frame["flood_occurrence"].isin([0, 1]).all():
        raise ValueError("Flood occurrence labels must be exactly 0 or 1.")
    if (
        not np.isfinite(label_frame["label_confidence"].to_numpy(dtype=float)).all()
        or not label_frame["label_confidence"].between(0, 1).all()
    ):
        raise ValueError("Label confidence must be finite and between 0 and 1.")
    label_frame["coverage_complete"] = [
        _parse_boolean(value, "coverage_complete")
        for value in label_frame["coverage_complete"]
    ]
    if (
        label_frame.loc[label_frame["flood_occurrence"] == 0, "coverage_complete"]
        .eq(False)
        .any()
    ):
        raise ValueError(
            "A negative flood label requires documented complete observation coverage; "
            "absence of an event record is not a negative label."
        )

    label_keys = [
        "location_id",
        "target_window_start_utc",
        "target_window_end_utc",
    ]
    conflicting_groups = (
        label_frame.groupby(label_keys, dropna=False)["flood_occurrence"].nunique().gt(1)
    )
    conflicting_count = int(conflicting_groups.sum())
    if conflicting_count:
        raise ValueError(f"Found {conflicting_count} conflicting location/window label groups.")
    duplicate_count = int(label_frame.duplicated(label_keys, keep="first").sum())
    label_frame = (
        label_frame.sort_values([*label_keys, "label_source", "source_record_id"])
        .drop_duplicates(label_keys, keep="first")
        .reset_index(drop=True)
    )

    predictor_frame = predictors.copy()
    predictor_frame["candidate_target_window_start_utc"] = pd.to_datetime(
        predictor_frame["candidate_target_window_start_utc"], errors="coerce", utc=True
    )
    predictor_frame["candidate_target_window_end_utc"] = pd.to_datetime(
        predictor_frame["candidate_target_window_end_utc"], errors="coerce", utc=True
    )
    predictor_keys = [
        "location_id",
        "candidate_target_window_start_utc",
        "candidate_target_window_end_utc",
    ]
    if predictor_frame.duplicated(predictor_keys).any():
        raise ValueError("Predictor table contains ambiguous duplicate location/window rows.")
    renamed_labels = label_frame.rename(
        columns={
            "target_window_start_utc": "candidate_target_window_start_utc",
            "target_window_end_utc": "candidate_target_window_end_utc",
        }
    )
    joined = predictor_frame.merge(
        renamed_labels,
        on=predictor_keys,
        how="inner",
        validate="one_to_one",
    )
    label_keys_for_join = renamed_labels.loc[:, predictor_keys]
    predictor_keys_for_join = predictor_frame.loc[:, predictor_keys]
    label_key_set = set(map(tuple, label_keys_for_join.itertuples(index=False, name=None)))
    predictor_key_set = set(map(tuple, predictor_keys_for_join.itertuples(index=False, name=None)))
    return joined, {
        "input_label_records": len(labels),
        "duplicate_label_records": duplicate_count,
        "conflicting_label_groups": conflicting_count,
        "unmatched_label_records": len(renamed_labels) - len(label_key_set & predictor_key_set),
        "matched_labeled_rows": len(joined),
        "positive_label_count": int(joined["flood_occurrence"].eq(1).sum()),
        "negative_label_count": int(joined["flood_occurrence"].eq(0).sum()),
    }


def build_predictor_dataset(
    raw_path: str | Path = DEFAULT_RAW,
    output_path: str | Path = DEFAULT_OUTPUT,
    *,
    labels_path: str | Path | None = None,
    approved_target_path: str | Path | None = None,
) -> dict[str, Any]:
    source_path = Path(raw_path)
    output = Path(output_path)
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    frame, quality = build_predictor_frame(payload)
    complete = frame.loc[:, FEATURE_COLUMNS].notna().all(axis=1)
    processed = frame.loc[complete].copy()
    output.parent.mkdir(parents=True, exist_ok=True)
    processed.to_csv(output, index=False, lineterminator="\n", float_format="%.6f")
    csv_hash = _sha256(output)
    source_manifest_path = source_path.with_suffix(".manifest.json")
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    label_quality = {
        "input_label_records": 0,
        "duplicate_label_records": 0,
        "conflicting_label_groups": 0,
        "unmatched_label_records": 0,
        "matched_labeled_rows": 0,
        "positive_label_count": 0,
        "negative_label_count": 0,
    }
    if (labels_path is None) != (approved_target_path is None):
        raise ValueError("--labels and --approved-target must be provided together.")
    labeled_output_path: Path | None = None
    label_manifest_path: Path | None = None
    if labels_path is not None and approved_target_path is not None:
        labels_file = Path(labels_path)
        approved_target = json.loads(Path(approved_target_path).read_text(encoding="utf-8"))
        labels_frame = pd.read_csv(
            labels_file,
            dtype={"location_id": "string", "source_record_id": "string"},
        )
        joined, label_quality = align_explicit_labels(processed, labels_frame, approved_target)
        if joined.empty:
            raise ValueError("No labels exactly match complete predictor rows and target windows.")
        labeled_output_path = output.with_name(f"{output.stem}_labeled_candidates.csv")
        joined.to_csv(
            labeled_output_path,
            index=False,
            lineterminator="\n",
            float_format="%.6f",
        )
        label_manifest_path = labeled_output_path.with_suffix(".manifest.json")
        _write_json(
            label_manifest_path,
            {
                "manifest_version": "1.0",
                "dataset_name": "Explicitly labeled flood training candidates",
                "dataset_version": SCHEMA_VERSION,
                "target_definition": approved_target,
                "target_definition_status": "USER_APPROVED_REQUIRES_SOURCE_AUDIT",
                "labels_file": labels_file.name,
                "labels_sha256": _sha256(labels_file),
                "predictor_file": output.name,
                "predictor_sha256": csv_hash,
                "row_count": len(joined),
                "column_count": len(joined.columns),
                "dataset_sha256": _sha256(labeled_output_path),
                "label_quality": label_quality,
                "training_suitable": False,
                "training_limitation": (
                    "Code validates exact keys and provenance fields but cannot authenticate the label source "
                    "or determine whether declared coverage and target definitions are scientifically correct."
                ),
            },
        )
        quality.update(label_quality)
        quality["label_source_status"] = "USER_PROVIDED_REQUIRES_SOURCE_AUDIT"
    manifest = {
        "manifest_version": "1.0",
        "dataset_name": "Kochi historical environmental predictor candidates",
        "dataset_version": SCHEMA_VERSION,
        "source_name": source_manifest["source_name"],
        "source_manifest": source_manifest_path.name,
        "source_manifest_sha256": _sha256(source_manifest_path),
        "source_raw_file": source_path.name,
        "source_raw_sha256": _sha256(source_path),
        "requested_location_wgs84": source_manifest["requested_location_wgs84"],
        "returned_grid_location_wgs84": source_manifest["returned_grid_location_wgs84"],
        "temporal_coverage": {
            "start": processed["feature_day_utc"].min() if not processed.empty else None,
            "end": processed["feature_day_utc"].max() if not processed.empty else None,
        },
        "spatial_resolution": source_manifest["spatial_resolution"],
        "temporal_resolution": "Daily UTC, trailing features available at next-day issue time",
        "target_definition": None,
        "target_definition_status": TARGET_DEFINITION_STATUS,
        "feature_schema": list(FEATURE_SCHEMA),
        "feature_order": list(FEATURE_COLUMNS),
        "row_count": len(processed),
        "column_count": len(processed.columns),
        "dataset_sha256": csv_hash,
        "training_suitable": False,
        "license": source_manifest["license"],
        "data_quality": quality,
        "label_quality": label_quality,
        "labeled_candidates_file": labeled_output_path.name if labeled_output_path else None,
        "labeled_candidates_manifest": label_manifest_path.name if label_manifest_path else None,
    }
    _write_json(output.with_suffix(".manifest.json"), manifest)
    _write_json(output.with_name(f"{output.stem}.quality.json"), quality)
    return {"manifest": manifest, "quality": quality}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create historical environmental predictors only; this does not create flood labels."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_RAW)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--labels", type=Path)
    parser.add_argument("--approved-target", type=Path)
    args = parser.parse_args()
    try:
        result = build_predictor_dataset(
            args.input,
            args.output,
            labels_path=args.labels,
            approved_target_path=args.approved_target,
        )
    except (OSError, ValueError, KeyError, json.JSONDecodeError, pd.errors.ParserError) as error:
        parser.error(str(error))
    print(
        json.dumps(
            {
                "output": str(args.output),
                "rows": result["manifest"]["row_count"],
                "dataset_sha256": result["manifest"]["dataset_sha256"],
                "quality_report": str(args.output.with_name(f"{args.output.stem}.quality.json")),
                "target_definition_status": result["quality"]["target_definition_status"],
                "training_status": result["quality"]["training_status"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
