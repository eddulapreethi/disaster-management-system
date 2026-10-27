# Historical analytics and ML pipeline execution report

## Result

The historical descriptive-analytics pipeline completed successfully. It scanned 8,810 rows from six manifest-validated processed EM-DAT extracts and found 8,810 unique event IDs with no cross-extract overlap. It rejected zero rows.

The pipeline does **not** train a model. The available source data does not include an approved site-level flood target, verified negative monitoring coverage, or historical environment values spatially and temporally joined to the events. No labels or measurements were fabricated.

## Acquisition workflow update

The manual acquisition path now accepts the inspected NWDP/CWC hourly CSV field names through `ml.preprocessing.normalize_nwdp_observations`. It requires an explicit site map keyed by station, state/district LGD codes, and exact coordinates; applies an operator-specified source timezone; preserves the untouched raw export; and writes hashes in a conversion manifest. It does not infer a stable gauge ID, datum, or QC. The existing environmental processor accepts an authorized Open-Meteo Archive JSON response with its sidecar manifest and produces the six candidate predictors; the configured Kochi location remains only one point and does not provide multi-gauge coverage.

Illustrative CSV templates are in `ml/preprocessing/templates/`; they contain `ILLUSTRATIVE_ONLY`/`UNVERIFIED` sentinels and are not source data. The readiness report now lists distinct missing or unverified requirements for danger-level authority, vertical datum agreement, complete monitoring coverage, candidate negative checks, gauge/grid review, historical weather coverage, license evidence, domain target approval, and model evaluation. Syntax status, source verification, and scientific review are reported separately. Readiness remains hard-coded to `NOT_READY`.

No CWC/NWDP historical file, danger-level register, coverage evidence, Open-Meteo archive, license authorization, or new labeled dataset was obtained during this continuation. No source was downloaded, no label was generated, and no model was trained or evaluated.

## Model selection and blockers

- No operational model was selected or trained; therefore there are no model evaluation metrics to report. The existing RandomForestRegressor is a legacy continuous-index path, not an approved flood classifier, and prediction remains disabled.
- The proposed first target is a named CWC/NWDP gauge reaching/exceeding its effective official danger level in the 24-hour UTC window beginning at issue time. It is explicitly `PROPOSED_REQUIRES_DOMAIN_APPROVAL` and describes a gauge warning, not general inundation or a calibrated probability.
- The EM-DAT extracts contain 4,291 reported flood events, but only 1,006 (23.44%) have valid coordinates. They do not establish monitored non-flood periods or match the available environment tables by verified location and prediction window.
- Available snapshots include 76 weather observations dated 2026-10-06 through 2026-10-11 and 17,957 hydrological observations dated 2025-12-31 through 2026-09-27. Both snapshots are stale relative to 2026-10-27 and neither is a labeled, aligned training set.
- The weather extract covers 8 configured locations, has valid coordinates for all 76 rows, and has no missing values in its exported fields. The hydrology extract covers 32 gauges from two configured sources with valid coordinates for all 17,957 rows; 723 water-level values are missing, rainfall is missing in 17,234 rows (95.97%), and discharge is entirely unavailable (17,957/17,957 missing). Geographic coverage is limited to the configured station/point extent recorded in the source manifests, not a continuous surface.
- The source manifests state that redistribution/license terms are unverified for both snapshots. The weather source is provider current-observation data, not a historical archive; the hydrology source has hourly-labeled telemetry with possible publication delay. Neither snapshot supplies the target labels or negative-coverage evidence.
- The hydrology snapshot has no authoritative per-gauge danger-level history or complete-coverage evidence. No reviewed gauge-to-grid crosswalk or verified 24-hour gauge-window label file exists. Therefore, reliable negative examples are not available.
- The configured Open-Meteo historical archive file and trained model artifact are absent. Satellite and GIS dataset folders contain documentation but no model feature datasets.
- Source verification on 2026-10-27 confirmed CWC-authored public NWDP catalog metadata for hourly gauge resources. Catalog listings include Subernarekha files labeled 1961–1990 and 1991–2020 and the current 2026–2030 telemetry resource. The inspected small 1961–1990 CSV response contained sparse records dated 1969–1975; NWDP metadata leaves its quality and validation method unspecified and calls its license only “Other (Open).” No local/raw source file was saved. The larger 1991–2020 file was not downloaded.
- The live NWDP datastore returned one CWC Krishna-basin telemetry row for Yadgir with an observation time of 2026-10-23 10:00 (source-local representation), station coordinates and water-level value. This verifies a current public API response only, not the full historical series, its observation completeness, the measurement datum, or a historical danger-level register.
- The official CWC Flood Forecasting portal was reachable, but an exact NWDP search did not find a dedicated danger-level register. No effective-dated gauge danger-level data or explicit reuse terms were verified. Open-Meteo documents its historical API data under CC BY 4.0 with attribution, while free API terms are non-commercial and commercial access requires an applicable subscription; no Open-Meteo archive was downloaded. Copernicus ERA5-Land was verified as a global hourly reanalysis from 1950 at 0.1-degree distribution grid (native about 9 km), but its values are estimates and no product was downloaded.
- Added `ml.preprocessing.flood_training_data_import`: the manual validator checks timestamp/timezone alignment, threshold effective intervals and vertical datums, source quality, duplicate observations, cadence-complete coverage, exact predictor windows, and reviewed gauge/grid mappings. It hashes inputs and reports assessments only; it has no final target column and cannot promote readiness.
- A reproducible candidate feature builder and strict label-alignment path now describe the proposed target. They require exact UTC 24-hour windows, stage/threshold-consistent class labels, gauge IDs, reviewed crosswalk reference, and explicit coverage evidence for negatives. These checks do not authenticate the external source or replace domain review.
- Backend readiness reports separate acquisition requirements and stays `NOT_READY`; the prediction API remains unavailable rather than emitting a fabricated risk.
- `pandas`, `numpy`, `scikit-learn`, and `joblib` are installed; `xgboost` and `shap` are unavailable in the checked runtime. Neither comparison model nor SHAP explanation is produced without a suitable approved training set and validated model.

## Reproduction and outputs

From the repository root:

```powershell
python -m ml.preprocessing.historical_analytics
```

Generated files:

- `ml/datasets/historical_data/analytics/historical_analytics.json`
- `ml/datasets/historical_data/analytics/historical_analytics.manifest.json`

Manifest verification:

- Transformation version: `emdat-historical-analytics-v1`
- Source rows scanned: 8,810
- Unique event IDs: 8,810
- Rejected rows: 0
- Deterministic output: true
- Output SHA-256: `24f1d441122dd96e0257a029321a8c297b4af68dae506a33232207c475a6e012`

The processor checks CSV, processed-input and workbook hashes against manifests before using them. Derived category-extract CSV dataset hashes use canonical LF line endings, which preserves the original manifest evidence across Git's Windows `core.autocrlf` conversion; processed-input and workbook hashes remain byte-for-byte checks. It writes derived analytics only; original source CSVs and workbook are inputs and are not rewritten.

## Readiness verification

The local readiness service returned:

| Readiness | Result |
|---|---|
| Historical analytics | `READY` |
| Historical source manifests | `VALIDATED` (6 datasets) |
| Supervised training | `NOT_READY` |
| Candidate feature contract | `VALIDATED`, candidate-only |
| Flood target and labels | `NOT_READY`; proposed target, no verified labels/negative coverage |
| Live runtime feature builder | `NOT_READY` |
| Compatible trained model | `NOT_READY` |
| Prediction | `NOT_READY`; automatic prediction disabled |

The prediction endpoint continues to reject unavailable flood inference rather than saving a heuristic score. Historical analytic availability must not open the ML prediction gate.

No live EM-DAT refresh was requested or performed. The latest event date represented by the supplied extracts is 2026-11-10 (storms/cyclones); this is an event date in a supplied historical dataset, not evidence that EM-DAT published a newer record during this run. There is no corresponding “latest stored observation” for EM-DAT analytics. Runtime weather and CWC observations remain governed by their separate observation-time freshness checks.

## Regression and build verification

Commands executed from the repository root (or `frontend` for npm):

| Check | Result |
|---|---|
| Complete backend and ML suite: `python -m pytest backend\tests ml -q` | 214 passed, 1 skipped |
| Frontend tests and production build | Not rerun; this continuation changed only Python backend/ML code and documentation |
| `git diff --check` | Passed; Git reported an existing line-ending normalization warning in an unrelated frontend file |

The `feature_contract.json` test checks feature order, source, units, candidate inference availability, and agreement with the Python feature schema. Readiness tests assert that model and prediction remain blocked.

## Remaining work

Prediction requires domain approval of target semantics, a dated official danger-level register with matching vertical datum, authorized and sufficiently representative multi-gauge observations, source quality and complete negative-coverage evidence, a reviewed gauge/catchment-to-weather-grid crosswalk, a verified spatial/temporal join, a compatible runtime builder, leakage-resistant evaluation, and reviewed model/artifact metrics. EM-DAT access terms also need to be followed when redistributing the source or derived data. See `docs/FLOOD_DATA_IMPORT_GUIDE.md`, `docs/FEATURE_CONTRACT.md`, and `docs/REMAINING_ML_BLOCKERS.md`.
