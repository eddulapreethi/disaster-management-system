from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from ml.preprocessing.flood_environmental_dataset import (
    FEATURE_COLUMNS,
    FEATURE_SCHEMA,
    LABEL_COLUMNS,
    TARGET_DEFINITION,
    TARGET_GEOGRAPHIC_UNIT,
    TARGET_ID,
    TARGET_NEGATIVE_DEFINITION,
    TARGET_POSITIVE_DEFINITION,
    align_explicit_labels,
    build_predictor_dataset,
    build_predictor_frame,
    validate_feature_schema,
)


def archive_payload(day_count: int = 10) -> dict:
    dates = pd.date_range("2020-01-01", periods=day_count, freq="D")
    values = list(range(day_count))
    return {
        "latitude": 9.947276,
        "longitude": 76.29921,
        "timezone": "GMT",
        "utc_offset_seconds": 0,
        "daily_units": {
            "temperature_2m_mean": "°C",
            "precipitation_sum": "mm",
            "relative_humidity_2m_mean": "%",
            "wind_speed_10m_max": "km/h",
        },
        "daily": {
            "time": dates.strftime("%Y-%m-%d").tolist(),
            "temperature_2m_mean": [27.0 + value / 10 for value in values],
            "precipitation_sum": [float(value + 1) for value in values],
            "relative_humidity_2m_mean": [75 + value for value in values],
            "wind_speed_10m_max": [10 + value for value in values],
        },
    }


def approved_target() -> dict:
    return {
        "status": "APPROVED",
        "target_id": TARGET_ID,
        "definition": TARGET_DEFINITION,
        "geographic_unit": TARGET_GEOGRAPHIC_UNIT,
        "prediction_horizon_hours": 24,
        "positive_label_definition": TARGET_POSITIVE_DEFINITION,
        "negative_label_definition": TARGET_NEGATIVE_DEFINITION,
        "location_crosswalk_reference": "reviewed-gauge-grid-crosswalk-v1",
        "approval_reference": "reviewed-target-spec-v1",
    }


def labels_for(predictor_rows: pd.DataFrame) -> pd.DataFrame:
    selected = predictor_rows.iloc[:2]
    rows = []
    for index, row in selected.iterrows():
        rows.append(
            {
                "gauge_id": f"gauge-{index}",
                "grid_location_id": row["location_id"],
                "location_crosswalk_reference": "reviewed-gauge-grid-crosswalk-v1",
                "target_window_start_utc": row["candidate_target_window_start_utc"],
                "target_window_end_utc": row["candidate_target_window_end_utc"],
                "flood_occurrence": int(index == selected.index[-1]),
                "label_source": "official-monitoring-record",
                "source_record_id": f"record-{index}",
                "label_method": "gauge stage compared with effective danger level",
                "label_confidence": 1.0,
                "observed_max_water_level_m": 21.0 if index == selected.index[-1] else 12.0,
                "official_danger_level_m": 20.0,
                "danger_level_source": "CWC danger-level register row",
                "coverage_complete": True,
                "coverage_evidence_reference": "gauge-window-coverage-record.csv",
            }
        )
    return pd.DataFrame(rows, columns=LABEL_COLUMNS)


def test_feature_schema_has_versioned_provenance_and_runtime_availability() -> None:
    validate_feature_schema()
    assert len(FEATURE_COLUMNS) == 6
    assert all(feature["source"] and feature["unit"] for feature in FEATURE_SCHEMA)
    assert all(feature["available_at_training"] for feature in FEATURE_SCHEMA)
    assert not any(feature["available_at_inference"] for feature in FEATURE_SCHEMA)


def test_machine_readable_contract_matches_candidate_feature_schema() -> None:
    contract_path = Path(__file__).with_name("feature_contract.json")
    contract = json.loads(contract_path.read_text(encoding="utf-8"))

    assert contract["schema_version"] == "flood-environmental-predictors-v1"
    assert contract["status"] == "CANDIDATE_NOT_READY_FOR_TRAINING_OR_INFERENCE"
    assert contract["target"]["target_id"] == TARGET_ID
    assert contract["target"]["definition"] == TARGET_DEFINITION
    assert contract["target"]["prediction_horizon_hours"] == 24
    assert contract["target"]["status"] == "PROPOSED_REQUIRES_DOMAIN_APPROVAL"
    assert contract["legacy_schema"]["status"] == "RETIRED_FROM_ACTIVE_INFERENCE"
    assert contract["feature_order"] == list(FEATURE_COLUMNS)
    assert [
        (feature["name"], feature["unit"], feature["source"], feature["available_at_inference"])
        for feature in contract["features"]
    ] == [
        (feature["name"], feature["unit"], feature["source"], feature["available_at_inference"])
        for feature in FEATURE_SCHEMA
    ]
    with pytest.raises(ValueError, match="unique"):
        validate_feature_schema((FEATURE_SCHEMA[0], FEATURE_SCHEMA[0]))


def test_predictor_features_are_trailing_only_and_time_aligned() -> None:
    payload = archive_payload()
    payload["daily"]["precipitation_sum"][6] = 700.0
    frame, quality = build_predictor_frame(payload)

    day_six = frame.iloc[5]
    day_seven = frame.iloc[6]
    assert day_six["antecedent_precipitation_1d_mm"] == 6.0
    assert day_six["antecedent_precipitation_3d_mm"] == 15.0
    assert pd.isna(day_six["antecedent_precipitation_7d_mm"])
    assert day_seven["antecedent_precipitation_7d_mm"] == 700.0 + sum([1, 2, 3, 4, 5, 6])
    assert day_six["prediction_issue_time_utc"] == "2020-01-07T00:00:00Z"
    assert day_six["candidate_target_window_start_utc"] == "2020-01-07T00:00:00Z"
    assert day_six["candidate_target_window_end_utc"] == "2020-01-08T00:00:00Z"
    assert quality["usable_predictor_rows"] == 4
    assert quality["target_leakage_check"]["status"] == "PASSED_FOR_FEATURE_WINDOWS"
    assert quality["positive_label_count"] == quality["negative_label_count"] == 0


def test_predictor_validation_rejects_duplicate_dates_bad_units_and_bad_values() -> None:
    payload = archive_payload()
    payload["daily"]["time"][1] = payload["daily"]["time"][0]
    with pytest.raises(ValueError, match="duplicate days"):
        build_predictor_frame(payload)

    payload = archive_payload()
    payload["daily_units"]["temperature_2m_mean"] = "F"
    with pytest.raises(ValueError, match="expected '°C'"):
        build_predictor_frame(payload)

    payload = archive_payload()
    payload["daily"]["precipitation_sum"][0] = -1
    with pytest.raises(ValueError, match="below its valid range"):
        build_predictor_frame(payload)

    payload = archive_payload()
    payload["timezone"] = "Asia/Kolkata"
    with pytest.raises(ValueError, match="Only UTC"):
        build_predictor_frame(payload)


def test_missing_calendar_day_breaks_rolling_window_instead_of_bridging_gap() -> None:
    payload = archive_payload()
    payload["daily"]["time"].pop(4)
    for variable in payload["daily_units"]:
        payload["daily"][variable].pop(4)

    frame, quality = build_predictor_frame(payload)

    assert quality["missing_calendar_days"] == ["2020-01-05"]
    assert pd.isna(frame.loc[6, "antecedent_precipitation_3d_mm"])
    assert quality["excluded_incomplete_predictor_rows"] == 7


def test_explicit_label_join_requires_exact_provenance_and_complete_negatives() -> None:
    predictors, _ = build_predictor_frame(archive_payload())
    predictors = predictors.loc[predictors.loc[:, FEATURE_COLUMNS].notna().all(axis=1)]
    joined, quality = align_explicit_labels(predictors, labels_for(predictors), approved_target())

    assert quality["matched_labeled_rows"] == 2
    assert quality["positive_label_count"] == 1
    assert quality["negative_label_count"] == 1
    assert "source_record_id" in joined.columns

    incomplete_negative = labels_for(predictors)
    incomplete_negative.loc[0, "coverage_complete"] = False
    with pytest.raises(ValueError, match="complete observation coverage"):
        align_explicit_labels(predictors, incomplete_negative, approved_target())

    with pytest.raises(ValueError, match="explicitly approved"):
        align_explicit_labels(predictors, labels_for(predictors), {"status": "UNSELECTED"})


def test_duplicate_and_conflicting_labels_are_counted_or_rejected() -> None:
    predictors, _ = build_predictor_frame(archive_payload())
    predictors = predictors.loc[predictors.loc[:, FEATURE_COLUMNS].notna().all(axis=1)]
    labels = labels_for(predictors)
    duplicate_labels = pd.concat([labels, labels.iloc[[0]]], ignore_index=True)

    _, quality = align_explicit_labels(predictors, duplicate_labels, approved_target())
    assert quality["duplicate_label_records"] == 1
    assert quality["matched_labeled_rows"] == 2

    conflict = labels.iloc[[0]].copy()
    conflict.loc[:, "flood_occurrence"] = 1
    conflict.loc[:, "coverage_complete"] = True
    conflict.loc[:, "observed_max_water_level_m"] = 21.0
    with pytest.raises(ValueError, match="conflicting location/window"):
        align_explicit_labels(
            predictors,
            pd.concat([labels.iloc[[0]], conflict], ignore_index=True),
            approved_target(),
        )


def test_deterministic_predictor_build_writes_manifest_and_quality_report(tmp_path) -> None:
    raw = tmp_path / "archive.json"
    raw.write_text(json.dumps(archive_payload()), encoding="utf-8")
    raw.with_suffix(".manifest.json").write_text(
        json.dumps(
            {
                "source_name": "Open-Meteo Historical Weather API",
                "requested_location_wgs84": {"latitude": 9.9312, "longitude": 76.2673},
                "returned_grid_location_wgs84": {"latitude": 9.947276, "longitude": 76.29921},
                "spatial_resolution": "Provider grid point.",
                "license": "Terms require confirmation.",
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "processed" / "predictors.csv"

    first = build_predictor_dataset(raw, output)
    csv_bytes = output.read_bytes()
    manifest_bytes = output.with_suffix(".manifest.json").read_bytes()
    second = build_predictor_dataset(raw, output)

    assert output.read_bytes() == csv_bytes
    assert output.with_suffix(".manifest.json").read_bytes() == manifest_bytes
    assert first["manifest"]["dataset_sha256"] == second["manifest"]["dataset_sha256"]
    assert first["manifest"]["row_count"] == 4
    assert first["manifest"]["training_suitable"] is False
    assert first["manifest"]["target_definition"] == TARGET_DEFINITION
    assert first["quality"]["training_status"] == "NOT_READY"
    assert output.with_name("predictors.quality.json").is_file()


def test_label_join_rejects_partial_and_nonmatching_windows() -> None:
    predictors, _ = build_predictor_frame(archive_payload())
    predictors = predictors.loc[predictors.loc[:, FEATURE_COLUMNS].notna().all(axis=1)]
    labels = labels_for(predictors)
    labels.loc[0, "target_window_start_utc"] = "2020-01-09T00:00:00Z"
    with pytest.raises(ValueError, match="24-hour UTC window"):
        align_explicit_labels(predictors, labels, approved_target())

    labels = labels_for(predictors)
    labels.loc[0, "target_window_start_utc"] = "2020-01-06T00:00:00+05:30"
    labels.loc[0, "target_window_end_utc"] = "2020-01-07T00:00:00+05:30"
    joined, quality = align_explicit_labels(predictors, labels, approved_target())
    assert quality["unmatched_label_records"] == 1
    assert len(joined) == 1


def test_label_join_rejects_unsupported_target_and_invalid_observations() -> None:
    predictors, _ = build_predictor_frame(archive_payload())
    predictors = predictors.loc[predictors.loc[:, FEATURE_COLUMNS].notna().all(axis=1)]
    labels = labels_for(predictors)

    wrong_target = approved_target()
    wrong_target["target_id"] = "unreviewed-target"
    with pytest.raises(ValueError, match="does not match the versioned"):
        align_explicit_labels(predictors, labels, wrong_target)

    below_danger_positive = labels.copy()
    below_danger_positive.loc[1, "observed_max_water_level_m"] = 19.9
    with pytest.raises(ValueError, match="Positive labels require a measured stage"):
        align_explicit_labels(predictors, below_danger_positive, approved_target())

    negative_at_danger = labels.copy()
    negative_at_danger.loc[0, "observed_max_water_level_m"] = 20.0
    with pytest.raises(ValueError, match="Negative labels cannot include"):
        align_explicit_labels(predictors, negative_at_danger, approved_target())

    missing_coverage_reference = labels.copy()
    missing_coverage_reference.loc[0, "coverage_evidence_reference"] = ""
    with pytest.raises(ValueError, match="coverage_evidence_reference"):
        align_explicit_labels(predictors, missing_coverage_reference, approved_target())

    naive_timestamp = labels.copy()
    naive_timestamp.loc[0, "target_window_start_utc"] = "2020-01-08T00:00:00"
    with pytest.raises(ValueError, match="timezone offset"):
        align_explicit_labels(predictors, naive_timestamp, approved_target())

    invalid_coordinates = predictors.copy()
    invalid_coordinates.loc[invalid_coordinates.index[0], "grid_latitude"] = 91
    with pytest.raises(ValueError, match="valid WGS 84 bounds"):
        align_explicit_labels(invalid_coordinates, labels, approved_target())

    incorrect_crosswalk = labels.copy()
    incorrect_crosswalk.loc[0, "location_crosswalk_reference"] = "different-crosswalk"
    with pytest.raises(ValueError, match="exact reviewed gauge-to-grid crosswalk"):
        align_explicit_labels(predictors, incorrect_crosswalk, approved_target())


def test_label_join_supports_multiple_gauges_per_weather_grid() -> None:
    predictors, _ = build_predictor_frame(archive_payload())
    predictors = predictors.loc[predictors.loc[:, FEATURE_COLUMNS].notna().all(axis=1)]
    labels = labels_for(predictors)
    second_gauge = labels.iloc[[0]].copy()
    second_gauge.loc[:, "gauge_id"] = "another-gauge-on-same-grid"

    joined, quality = align_explicit_labels(
        predictors,
        pd.concat([labels, second_gauge], ignore_index=True),
        approved_target(),
    )

    assert len(joined) == 3
    assert quality["distinct_gauge_count"] == 3


def test_label_join_requires_issue_time_to_equal_target_window_start() -> None:
    predictors, _ = build_predictor_frame(archive_payload())
    predictors = predictors.loc[predictors.loc[:, FEATURE_COLUMNS].notna().all(axis=1)]
    predictors.loc[predictors.index[0], "prediction_issue_time_utc"] = "2020-01-08T01:00:00Z"

    with pytest.raises(ValueError, match="begin exactly at prediction issue time"):
        align_explicit_labels(predictors, labels_for(predictors), approved_target())
