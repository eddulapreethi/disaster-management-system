# Historical analytics and ML pipeline execution report

## Result

The historical descriptive-analytics pipeline completed successfully. It scanned 8,810 rows from six manifest-validated processed EM-DAT extracts and found 8,810 unique event IDs with no cross-extract overlap. It rejected zero rows.

The pipeline does **not** train a model. The available source data does not include an approved site-level flood target, verified negative monitoring coverage, or historical environment values spatially and temporally joined to the events. No labels or measurements were fabricated.

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

The processor checks CSV, processed-input and workbook hashes against manifests before using them. It writes derived analytics only; original source CSVs and workbook are inputs and are not rewritten.

## Readiness verification

The local readiness service returned:

| Readiness | Result |
|---|---|
| Historical analytics | `READY` |
| Historical source manifests | `VALIDATED` (6 datasets) |
| Supervised training | `NOT_READY` |
| Candidate feature contract | `VALIDATED`, candidate-only |
| Live runtime feature builder | `NOT_READY` |
| Compatible trained model | `NOT_READY` |
| Prediction | `NOT_READY`; automatic prediction disabled |

The prediction endpoint continues to reject unavailable flood inference rather than saving a heuristic score. Historical analytic availability must not open the ML prediction gate.

No live EM-DAT refresh was requested or performed. The latest event date represented by the supplied extracts is 2026-11-10 (storms/cyclones); this is an event date in a supplied historical dataset, not evidence that EM-DAT published a newer record during this run. There is no corresponding “latest stored observation” for EM-DAT analytics. Runtime weather and CWC observations remain governed by their separate observation-time freshness checks.

## Regression and build verification

Commands executed from the repository root (or `frontend` for npm):

| Check | Result |
|---|---|
| Focused analytics, feature-contract, training, historical readiness/API and prediction readiness tests | 31 passed |
| Complete backend and ML suite: `python -m pytest backend\tests ml -q` | 157 passed, 1 skipped, 28 subtests passed |
| Frontend tests: `npm.cmd test` | 4 passed |
| Frontend production build: `npm.cmd run build` | Passed |
| `git diff --check` | Passed; existing line-ending normalization warning only |

The `feature_contract.json` test checks feature order, source, units, candidate inference availability, and agreement with the Python feature schema. Readiness tests assert that model and prediction remain blocked.

## Remaining work

Prediction requires domain approval of target semantics, authorized and sufficiently representative site-level observations, positive labels and complete negative-coverage evidence, a verified spatial/temporal join, a compatible runtime builder, leakage-resistant evaluation, and reviewed model/artifact metrics. EM-DAT access terms also need to be followed when redistributing the source or derived data. See `docs/ML_TASK_FEASIBILITY.md`, `docs/FEATURE_CONTRACT.md`, and `docs/REMAINING_ML_BLOCKERS.md`.
