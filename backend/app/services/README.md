# Weather Collection

The backend uses Open-Meteo's public forecast endpoint for current conditions. PostgreSQL/PostGIS is the authoritative application store; the collector does not write duplicate CSV files under `ml/datasets/weather/raw/`. `ml/datasets/weather/processed/` is reserved for later feature preparation and remains unpopulated by this task.

## Configuration

Copy `backend/.env.example` to `backend/.env` and configure:

- `WEATHER_LOCATION_NAME`, `WEATHER_LATITUDE`, `WEATHER_LONGITUDE`: the default monitored location (the example is Kochi; replace it with the study site).
- `WEATHER_LOCATIONS_JSON`: optional JSON array of named coordinates when multiple locations are required; when non-empty it takes precedence over the single-location settings.
- `WEATHER_POLL_INTERVAL_SECONDS`: positive integer, default `60`.
- `WEATHER_MAX_AGE_SECONDS`: positive integer, default `7200` (two hours). This allows delayed model updates while marking older readings stale.

Every 60 seconds means the backend checks for new data every 60 seconds. It does not mean Open-Meteo generates a new observation every 60 seconds.

## Collection and Storage

The FastAPI lifespan starts one background task. It polls once immediately, then repeats on the configured interval. Blocking HTTP and database work runs off the event loop. Recoverable request, validation, and database failures are logged and the collector retries on a later cycle; shutdown cancels the task cleanly.

Each row records `observation_time` from Open-Meteo, `fetched_at` when the backend fetched the response, and `created_at` when the database row was created. A unique `(station_id, observation_time, source)` database constraint and conflict-safe inserts prevent repeated observations from being stored. The source can continue returning the same observation time across multiple checks; those checks are counted as skipped duplicates.

For an existing PostgreSQL database, inspect possible duplicate rows and apply `database/migrations/003_weather_observation_dedup.sql` before using the updated collector. This migration deliberately stops if it finds duplicates; it does not delete data. New installations should use `database/schemas/weather_observations.sql`. SQLite local development gets the unique constraint through SQLAlchemy `create_all`; startup adds missing metadata columns to older SQLite tables without deleting rows. If an older SQLite database contains duplicate keys, those rows are retained, the upgrade does not create a unique index, and the single-process collector checks existing keys before writing. Resolve those historical duplicates deliberately before adding an index if multi-process collection is later required.

## Readiness and API

`GET /api/weather/latest` returns the latest stored record per configured location, including `observation_time`, `fetched_at`, `created_at`, and `source`.

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