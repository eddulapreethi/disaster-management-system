# End-to-end and verification report

**Run date:** 2026-10-11  
**Repository:** `disaster-management-system`, branch `preethi`

## Baseline recorded before implementation

- Backend and ML tests: **133 passed, 1 skipped**, 3 third-party SHAP deprecation warnings, 28 subtests passed.
- Frontend `npm.cmd run build`: succeeded with Vite 5.4.21.
- Existing app working tree had four untracked ML acquisition/predictor files; they were read and preserved. No pre-existing tracked modifications were present in the app repository.
- Known blockers from the code and docs: no flood model artifact or verified inference feature builder; CWC source observations are stale; PostgreSQL/PostGIS and provider-backed integrations were not deployment-verified.
- Initial frontend test script did not exist.

## Current automated checks

| Command | Result |
|---|---|
| `python -m pytest backend\tests ml -q` | **144 passed, 1 skipped**, 3 SHAP deprecation warnings, 28 subtests passed. Run with the project virtual environment's Python from the repository root. |
| `npm.cmd test` (from `frontend/`) | **4 passed, 0 failed, 0 skipped**. |
| `npm.cmd run build` (from `frontend/`) | **Passed**; Vite transformed 108 modules and generated the production bundle. |
| `python -c "import app.api.predictions"` (from `backend/`) | **Passed** using the documented backend working directory. |
| Pylance Problems check on touched backend service/schema/API files | No errors reported. |

The one skip is the opt-in live Ollama provider smoke test. It was not enabled, and no result is claimed for a live Ollama connection. SHAP emitted three pending-deprecation warnings from its installed plotting package; no test failed.

## Workflows covered by tests

- Hydrology timestamp normalization, malformed rows, deduplication, latest-observation freshness, empty/no-new-data reporting, and descending-ID pagination through a stored cursor.
- Flood model readiness gate and HTTP 503 behavior when no compatible artifact/runtime mapping is available.
- Environmental predictor rolling-window alignment and source-value preservation, including a 700 mm daily input.
- Resource stock exhaustion, insufficient inventory, shortage reporting, duplicate demand IDs and rollback after a simulated concurrent reservation conflict.
- Alert threshold validation, persistence and repeated-event suppression.
- UTC `Z` serialization for saved alert timestamps.
- Digital Twin bounded/finite input and deterministic formula checks.
- Frontend weather-to-simulation validation (real zero accepted; missing/non-finite measurements rejected) and alert API-field display formatting.
- GIS readiness checks for seven local layers and WGS 84/Kochi coverage.

## Live and integration verification limits

- Read-only calls to the official NWDP CKAN `resource_show` and `datastore_search` endpoints succeeded during review. This checked API response shape and the first `_id desc` rows, not the backend collector running against the provider.
- No real Open-Meteo acquisition, Ollama request, Copernicus authentication, SMS/email sender, PostgreSQL/PostGIS deployment, or browser-driven full application session was run.
- The React tests are focused Node unit tests, not component/browser tests. The production bundle builds, but this does not prove every page against a running API.
- No ML data acquisition or model training was run. The model readiness gate remains disabled.

## Changes made during this pass

- Removed the unsupported rainfall-value substitution in the pre-existing untracked predictor pipeline and added a regression assertion.
- Added resource inventory PATCH/DELETE routes and frontend edit/remove actions.
- Made stock deductions conditional and transaction-safe; multi-item plans roll back if inventory changed.
- Added demand-ID uniqueness validation.
- Made alert threshold configurable, added duplicate suppression, removed direct arbitrary alert creation, and aligned the alert card with the persisted API response.
- Prevented Digital Twin runs from substituting default values when current weather inputs are missing.
- Added explicit hydrology collection outcome labels separating an empty source response, unchanged records, inserted rows, duplicates and parse failures.
- Added frontend unit-test script and targeted tests.

No credentials, model artifacts, raw data, local database files or generated build outputs were added intentionally. No external services were configured during automated tests.
