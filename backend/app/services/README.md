# Weather Collection

The backend uses Open-Meteo's public forecast endpoint for current conditions. The application database is selected by `DATABASE_URL` (SQLite is the local default); the collector does not write duplicate CSV files under `ml/datasets/weather/raw/`. `ml/datasets/weather/processed/` contains an explicitly exported observation snapshot, not model features.

## Configuration

Copy `backend/.env.example` to `backend/.env` and configure:

- `WEATHER_LOCATION_NAME`, `WEATHER_LATITUDE`, `WEATHER_LONGITUDE`: the default monitored location (the example is Kochi; replace it with the study site).
- `WEATHER_LOCATIONS_JSON`: optional JSON array of named coordinates when multiple locations are required; when non-empty it takes precedence over the single-location settings.
- `WEATHER_POLL_INTERVAL_SECONDS`: positive integer, default `300` (five minutes).
- `WEATHER_MAX_AGE_SECONDS`: positive integer, default `7200` (two hours). This allows delayed model updates while marking older readings stale.

Every five minutes means the backend checks for new data every five minutes. It does not mean Open-Meteo generates a new observation every five minutes.

## Collection and Storage

The FastAPI lifespan starts one background task. It polls once immediately, then repeats on the configured interval. Blocking HTTP and database work runs off the event loop. Recoverable request, validation, and database failures are logged and the collector retries on a later cycle; shutdown cancels the task cleanly.

Only one cycle per source can run at a time in a process. Run one Uvicorn worker; multiple workers would create independent schedulers and duplicate polling.

Each row records `observation_time` from Open-Meteo, `fetched_at` when the backend fetched the response, and `created_at` when the database row was created. A unique `(station_id, observation_time, source)` database constraint and conflict-safe inserts prevent repeated observations from being stored. The source can continue returning the same observation time across multiple checks; those checks are counted as skipped duplicates.

For an existing PostgreSQL database, inspect possible duplicate rows and apply `database/migrations/003_weather_observation_dedup.sql` before using the updated collector. This migration deliberately stops if it finds duplicates; it does not delete data. New installations should use `database/schemas/weather_observations.sql`. SQLite local development gets the unique constraint through SQLAlchemy `create_all`; startup adds missing metadata columns to older SQLite tables without deleting rows. If an older SQLite database contains duplicate keys, those rows are retained, the upgrade does not create a unique index, and the single-process collector checks existing keys before writing. Resolve those historical duplicates deliberately before adding an index if multi-process collection is later required.

## Readiness and API

`GET /api/weather/latest` returns the latest stored record per configured location, including `observation_time`, `fetched_at`, `created_at`, and `source`.

`GET /api/weather/current?latitude=51.5072&longitude=-0.1276` requests fresh Open-Meteo current conditions for the authenticated user's selected coordinates. This on-demand endpoint is independent of `WEATHER_LOCATIONS_JSON`, validates the provider timestamp and required measurements, and returns an explicit error when the provider cannot serve the location. It does not create an observation record.

`GET /api/weather/status` reports:

- `READY`: a recent valid observation exists in the database and the latest collection cycle did not fail.
- `STALE`: a stored observation exists but is older than `WEATHER_MAX_AGE_SECONDS`.
- `UNAVAILABLE`: no valid observation has been stored and no failed latest attempt is recorded.
- `ERROR`: no observation is available, or the latest collection attempt failed (the last stored row, if any, remains visible).

`last_observation` is the provider's observation timestamp. `last_checked` is the latest completed polling cycle; `last_successful_fetch` can advance even if that cycle found only an already-stored observation. The existing `/api/data-readiness` response includes the same weather readiness evidence. These routes require the existing bearer-token authentication.

## Run and Verify

From `backend/` in PowerShell:

```powershell
Copy-Item .env.example .env
# Set DATABASE_URL and the weather coordinates in .env; keep .env uncommitted.
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

After registering/logging in and obtaining a bearer token, call:

```text
GET http://127.0.0.1:8000/api/weather/latest
GET http://127.0.0.1:8000/api/weather/status
GET http://127.0.0.1:8000/api/data-readiness
```

Run offline tests from `backend/` with `python -m pytest tests/test_weather_service.py -q`. Tests mock the source and do not call Open-Meteo.

The Digital Twin API fetches this same on-demand weather baseline on the backend, then saves the requested coordinates and provider observation time with each illustrative simulation. Flood scenarios may add a user-entered hypothetical rainfall amount; a percentage change to zero current precipitation remains zero. The output is weather-only and does not include hydrology, terrain, drainage, exposure, or a time-series rainfall window, so a zero score is not evidence of zero disaster risk.

The assistant stores its transcript and unsent prompt draft in per-tab `sessionStorage` so both are restored after route changes and refreshes, without persisting user conversations in the application database. Starting a new conversation or signing out clears both; common labeled credentials, bearer tokens, and recognizable key formats are redacted before browser persistence. Ollama's installed-model list is cached in backend memory for 20 seconds to avoid an extra local HTTP check on every prompt, and each chat request asks Ollama to keep the configured model loaded for ten minutes.

## NWDP/CWC Hydrology

The public NWDP collector uses descending `_id` pagination and a persisted per-resource high-water cursor. It retries a bounded number of times on request failures, does not overlap cycles within one process, and does not equate a successful source check with a fresh observation. `records_returned` is the count read from provider pages; `records_received` is new-to-cursor raw rows; `valid_records` counts normalized new rows; `inserted_count` excludes station/time duplicates. A provider can return no new rows while the last fetch is successful and the latest observation remains stale.

`GET /api/hydrology/status` exposes per-resource status, freshness, observation age, latest fetch, station identity, source update cadence, counts, parse errors, and whether an observation newer than the stored maximum was discovered. `GET /api/data-readiness` also includes GIS file validation and hash-checked EM-DAT manifests. Historical event files can validate as source datasets while remaining explicitly ineligible for model training. Both endpoints require the existing bearer-token authentication.

SQLite startup adds the diagnostic columns (`records_returned`, `valid_records`, `newer_observation_found`, and `last_error`) without deleting stored collection state. Existing PostgreSQL deployments must apply `database/migrations/004_hydrology_collection_diagnostics.sql` once before deploying code that reads the new columns. Verify the migration on a backup/staging database before applying it to production.

The local hydrology and weather exports are reproducible snapshots, not additional collectors. From the repository root, with `DATABASE_URL` selecting the intended application database:

```powershell
python -m ml.preprocessing.export_environmental_snapshots
```

The command reads database rows and writes CSV plus SHA-256 manifests under `ml/datasets/weather/processed/` and `ml/datasets/hydrological/processed/`. It does not update the source observations or assert that the exports are suitable training data. See [the acquisition/preparation report](../../../docs/DATA_ACQUISITION_AND_PREPARATION_REPORT.md) and [pipeline status report](../../../docs/HYDROLOGY_AND_DATA_PIPELINE_STATUS.md) for measured output and limitations.