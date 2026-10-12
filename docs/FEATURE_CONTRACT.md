# Flood environmental feature contract

## Status and version

The candidate schema is `flood-environmental-predictors-v1`, defined by `ml/preprocessing/flood_environmental_dataset.py` and summarized in the machine-readable `ml/preprocessing/feature_contract.json`.

Status: **candidate predictors only**. No target definition or forecast horizon has been approved. The predictors are not currently available at live inference, the runtime feature builder is unavailable, and this schema does not make training ready.

## Candidate predictors

All source values are daily Open-Meteo Archive best-match values at a provider-resolved grid point. Feature days are UTC, complete, and precede the issue time; future target-window measurements must never enter the feature vector.

| Order | Feature | Type and unit | Source | Aggregation / missing policy |
|---:|---|---|---|---|
| 1 | `antecedent_precipitation_1d_mm` | float, mm | `precipitation_sum` | Sum of the complete prior UTC day; require the source value. |
| 2 | `antecedent_precipitation_3d_mm` | float, mm | `precipitation_sum` | Trailing 3 complete UTC days; require all 3 values. |
| 3 | `antecedent_precipitation_7d_mm` | float, mm | `precipitation_sum` | Trailing 7 complete UTC days; require all 7 values. |
| 4 | `temperature_mean_c` | float, degC | `temperature_2m_mean` | Daily UTC mean; require the source value. |
| 5 | `relative_humidity_mean_percent` | float, % | `relative_humidity_2m_mean` | Daily UTC mean; require the source value. |
| 6 | `wind_speed_max_kmh` | float, km/h | `wind_speed_10m_max` | Daily UTC maximum; require the source value. |

The three precipitation features are sums of the source daily measurements, not hard-coded substitutes. Bounds and source checks are encoded in the Python schema; the machine-readable contract must remain synchronized with it. Requested and provider-returned coordinates, UTC feature/target windows, raw-source hash, and processing provenance belong in the dataset output/manifest, not in the model's numeric feature vector.

### Missing and unavailable input rules

- Do not impute incomplete feature windows into a valid prediction silently; the candidate builder excludes rows missing any required source day/value.
- Source metadata and provider-returned coordinates must be retained for audit. Provider grid resolution depends on the returned source response; it is not a claim of station-level measurement.
- These are historical archive predictors, not a live forecast feed. The contract sets `available_at_inference` to false for every feature.
- The target is explicitly unselected. No flood absence is inferred from missing EM-DAT rows.

## Retired legacy schema

The former `flood-risk-factors-v1` schema contains 20 0–16 numeric indices without documented authoritative units, sources, transformations, or mapping to measured observations. It is retired from active inference. No conversion from weather, hydrology, or EM-DAT fields to those indices is allowed without authoritative definitions and validation.

## Contract validation

Run the feature-builder tests:

```powershell
python -m pytest ml\preprocessing\test_flood_environmental_dataset.py -q
```

The test suite verifies the six ordered names, required source/unit metadata, candidate-only inference availability, and agreement between the Python schema and machine-readable JSON. Any schema change requires a version change, an updated test, and a compatible training/runtime contract. Prediction remains blocked until labels, inference-available inputs, a runtime builder, a compatible artifact, and all readiness checks are satisfied.
