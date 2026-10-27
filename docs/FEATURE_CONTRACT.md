# Flood environmental feature contract

## Status and version

The candidate schema is `flood-environmental-predictors-v1`, defined by `ml/preprocessing/flood_environmental_dataset.py` and summarized in the machine-readable `ml/preprocessing/feature_contract.json`.

Status: **candidate predictors only**. The first target is proposed, not domain-approved: predict for one identified CWC/NWDP river gauge whether its measured stage will reach or exceed its official danger level at any time in the 24-hour UTC window beginning at issue time. The geographic unit is the gauge, linked to one Open-Meteo grid point through a reviewed crosswalk. The predictors are not currently available at live inference, the runtime feature builder is unavailable, and this schema does not make training ready.

The target is a **gauge danger-level warning**, not a general flood/inundation label or a calibrated probability. A positive requires an observed stage at/above the gauge's danger level using the same verified vertical datum and units. A negative requires verified, complete gauge measurement coverage over the whole 24-hour window and every valid measurement below threshold. Missing event reports or missing telemetry never count as negatives. Domain approval, a dated official danger-level register, a reviewed gauge/grid crosswalk, and authorized source evidence are still required.

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
- The target definition is proposed and requires domain approval. The candidate builder accepts labels only when they match the versioned target, the exact 24-hour UTC interval, an explicit gauge ID, grid location ID, reviewed crosswalk reference, measured maximum stage and danger level, and documented evidence. It does not authenticate source quality or infer negatives.
- The training-data readiness check deliberately remains `NOT_READY`; the repository currently has no official danger-level table, reviewed crosswalk, verified window labels, or downloaded historical weather archive. The archive acquisition script keeps the Kochi point as its default and accepts alternate coordinates only when explicitly supplied with an output path. Coordinate selection does not establish gauge identity or catchment relevance.
- `ml/preprocessing/flood_training_data_import.py` validates manually obtained canonical source CSVs and writes hashed evidence assessments. It intentionally does not generate training targets or enable readiness. See [the source audit and import guide](./FLOOD_DATA_IMPORT_GUIDE.md) for official catalog findings, license/access caveats, schemas, and import commands.

### Data required before training

| Dataset/evidence | Current status | Use and limitations |
|---|---|---|
| EM-DAT historical extracts | Available; 4,291 reported flood records, 1,006 with valid coordinates (23.44%) | Descriptive event history only. No gauge-stage labels, complete event-free coverage, or exact daily local joins. A missing EM-DAT event is not a negative. |
| Open-Meteo Archive historical data | Acquisition/preparation code exists; the canonical archive at `ml/datasets/raw_sources/open_meteo/archive.json` is absent | Historical gridded archive data can support candidate weather inputs after license/source and gauge-to-grid review. The request asks for `best_match`, but returned model identity/native resolution are recorded only if explicitly present in the provider response. The existing weather snapshot is short and stale, not a training archive. |
| CWC/NWDP hydrology snapshot | Available in the repository as a historical observation extract | Contains water-level observations, but no authoritative per-gauge danger-level history, verified completeness coverage, or approved link to weather cells; unsuitable for verified labels as-is. |
| Gauge danger-level register | Missing | Must include stable gauge IDs, units, effective dates, authoritative source, quality control, and license/access permission. |
| Gauge-to-grid crosswalk | Missing | Must document gauge and weather-grid IDs/coordinates, matching method/tolerance, review, and source. |
| Explicit 24-hour gauge-window labels | Missing | Derive only from valid stage observations plus effective danger levels and complete coverage evidence; preserve source record IDs and timestamps. |

Once labels exist, evaluate with chronological holdouts and location/gauge-aware grouping (and event grouping where event IDs exist). Keep all windows for a gauge/event from leaking across partitions. Require enough independent gauges and both classes to make metrics meaningful; report precision, recall, F1, confusion matrix, class prevalence, and consequences of false alarms versus missed warnings. Random Forest is only a candidate baseline after those data checks pass; no model has been trained.

## Retired legacy schema

The former `flood-risk-factors-v1` schema contains 20 0–16 numeric indices without documented authoritative units, sources, transformations, or mapping to measured observations. It is retired from active inference. No conversion from weather, hydrology, or EM-DAT fields to those indices is allowed without authoritative definitions and validation.

## Contract validation

Run the feature-builder tests:

```powershell
python -m pytest ml\preprocessing\test_flood_environmental_dataset.py -q
```

The test suite verifies the six ordered names, required source/unit metadata, candidate-only inference availability, and agreement between the Python schema and machine-readable JSON. Any schema change requires a version change, an updated test, and a compatible training/runtime contract. Prediction remains blocked until labels, inference-available inputs, a runtime builder, a compatible artifact, and all readiness checks are satisfied.
