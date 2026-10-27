# DisasterGuard historical analytics and flood ML

## Current verified state

The six supplied EM-DAT extracts support descriptive historical analytics. The deterministic pipeline validates extract, processed-input, and source-workbook hashes against manifests and writes. Derived category-extract CSV hashes use canonical LF line endings to remain stable across Git's Windows `core.autocrlf` conversion; processed inputs and source workbooks remain byte-for-byte verified:

- `ml/datasets/historical_data/analytics/historical_analytics.json`
- `ml/datasets/historical_data/analytics/historical_analytics.manifest.json`

Run from the repository root:

```powershell
python -m ml.preprocessing.historical_analytics
```

The current extracts contain 8,810 rows and 8,810 unique event IDs, including 4,291 flood-classified records. Event coordinates and reported impacts are incomplete. Counts and impact sums are descriptive source reports; they are not complete surveillance, local flood labels, or model probabilities. Read [the dataset assessment](../docs/HISTORICAL_DATASET_ASSESSMENT.md) for exact coverage and provenance.

The source workbook is `ml/datasets/historical_disasters/EM-DAT/public_emdat_custom_request_2026-09-30_65676a52-2bac-4e9b-b454-70d54b055fa3.xlsx` and is subject to EM-DAT access terms. The presence of a local copy or derived report does not establish redistribution permission.

## Prediction readiness

There is no compatible trained model artifact. Supervised training, runtime feature generation, and prediction are `NOT_READY`; prediction requests remain unavailable (HTTP 503) and do not persist heuristic flood scores. Historical analytics being ready does not change these gates. Stored legacy prediction rows may contain demonstrator scores, not verified forecasts. Backend data readiness now reports the proposed flood target and the required missing evidence without treating file presence as model readiness.

The first proposed target is: for one identified CWC/NWDP river gauge, predict whether measured stage reaches/exceeds that gauge's official danger level at any time in the 24-hour UTC window beginning at issue time. It is a gauge-warning target, not a general inundation target, and still requires domain approval. No verified source/space/time join currently connects environmental data to these labels. Do not interpret a missing event record as a negative observation, convert observed weather/hydrology into the retired ordinal features, or treat a zero Digital Twin score as low real-world flood risk. See [ML task feasibility](../docs/ML_TASK_FEASIBILITY.md) and [remaining blockers](../docs/REMAINING_ML_BLOCKERS.md).

## Candidate environmental feature contract

The candidate schema `flood-environmental-predictors-v1` is implemented in `ml/preprocessing/flood_environmental_dataset.py` and mirrored by `ml/preprocessing/feature_contract.json`. For the proposed 24-hour gauge target, its candidate ordered features are:

1. `antecedent_precipitation_1d_mm` — prior complete UTC day precipitation sum (mm).
2. `antecedent_precipitation_3d_mm` — trailing three complete UTC days precipitation sum (mm).
3. `antecedent_precipitation_7d_mm` — trailing seven complete UTC days precipitation sum (mm).
4. `temperature_mean_c` — daily UTC mean 2 m temperature (degC).
5. `relative_humidity_mean_percent` — daily UTC mean 2 m relative humidity (%).
6. `wind_speed_max_kmh` — daily UTC maximum 10 m wind speed (km/h).

Source values are Open-Meteo Archive daily best-match data. Precipitation rolling windows require all days; no feature may use a future value. The builder retains source/response coordinates, time windows, and hashes as metadata. The contract marks all features unavailable for live inference; an approved target and compatible backend runtime feature builder do not exist. See [the detailed feature contract](../docs/FEATURE_CONTRACT.md).

The former `flood-risk-factors-v1` schema has 20 numeric 0–16 inputs without authoritative definitions, units, data sources, or transformations. It is retired from active inference; values from weather, hydrology, or EM-DAT must not be mapped to those indices speculatively.

### Label preparation and readiness

The reproducible predictor/optional label join is:

```powershell
python -m ml.preprocessing.flood_environmental_dataset --input <authorized-archive.json> --output <predictors.csv>
python -m ml.preprocessing.flood_environmental_dataset --input <authorized-archive.json> --output <predictors.csv> --labels <verified-gauge-window-labels.csv> --approved-target <domain-approved-target.json>
```

The optional join requires an exact target approval, gauge ID, weather grid ID, reviewed crosswalk reference, timezone-aware 24-hour target windows, measured maximum stage, official danger level, source record/provenance, and complete monitoring coverage plus a reference for every negative. It validates declared values and joins exactly; it cannot authenticate source licensing, the reviewer, the danger-level authority, or whether coverage is scientifically complete. It produces labeled *candidates*, never a trained dataset or model. Synthetic test fixtures are not real labels.

Current checked data: EM-DAT has 4,291 reported flood events, of which 1,006 have coordinates; it cannot supply negative periods. The checked hydrology extract has historical water-level observations, but lacks official per-gauge danger thresholds and complete-window monitoring evidence. The checked weather snapshot has only 76 observations dated 2026-10-06 through 2026-10-11, and is stale; the configured historical Open-Meteo archive is absent. No verified negative examples or usable aligned training labels are available. No model was trained or evaluated; there are no real metrics.

The backend exposes these blockers in `flood_training_data` readiness. Status remains `NOT_READY` until target approval, authorized historical inputs, validated labels/coverage, site-aware evaluation, and compatible inference are reviewed. Do not enable prediction based on candidate output alone.

The verified-source audit and canonical manual import procedure are documented in [the flood data import guide](../docs/FLOOD_DATA_IMPORT_GUIDE.md). The import utility hashes source inputs and assesses exact windows but does not produce model labels or change readiness.

## Training gate

Do not train or register an operational model until all of the following are evidenced and reviewed:

- an approved target definition, geographic unit, issue time, and forecast horizon;
- authorized, representative environmental observations aligned to verified positive flood labels;
- complete observation coverage supporting negative labels (absence from EM-DAT is not enough);
- an approved, versioned training schema and a matching inference-time feature builder;
- spatial/event-grouped and chronological leakage-resistant evaluation, with baseline and appropriate uncertainty/calibration metrics; and
- reproducible dataset/source hashes, licensing, preprocessing, split policy, metrics, and artifact compatibility checks.

Unit-test synthetic fixtures exercise implementation behavior only; they are not operational evidence and must never be placed at the configured model artifact path.

## Verification

From the repository root:

```powershell
python -m pytest backend\tests ml -q
```

From `frontend`:

```powershell
npm.cmd test
npm.cmd run build
```

The generated analytics execution and current test results are recorded in [the pipeline execution report](../docs/ML_PIPELINE_EXECUTION_REPORT.md).
