# DisasterGuard AI Backend

FastAPI backend for the DisasterGuard AI frontend. It has user authentication but does not use role-based access control.

## Setup (Windows)

From `C:\MajorProject\disaster-management-system\backend`:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create `.env` with a long random `JWT_SECRET_KEY`. To use trained flood-model inference, train or provide an artifact and set `DISASTERGUARD_MODEL_PATH` to its path. Without an artifact the prediction API records a clearly labeled weather heuristic and returns no SHAP values.

### Copernicus Sentinel access

Create a server-side OAuth client in the Copernicus Data Space dashboard under **User Settings → OAuth clients**. Add its values to local `backend/.env` as `COPERNICUS_CLIENT_ID` and `COPERNICUS_CLIENT_SECRET`; never put them in React or commit the `.env` file. `backend/.env.example` contains empty placeholders only. The backend caches the OAuth token and uses the official Sentinel Hub Catalog and Process APIs. No satellite data is available until a valid client is configured and authorized.

On backend startup, an asynchronous background worker fetches Open-Meteo current conditions immediately and polls every `WEATHER_POLL_INTERVAL_SECONDS` (default 60). Configure one study location with `WEATHER_LOCATION_NAME`, `WEATHER_LATITUDE`, and `WEATHER_LONGITUDE`; optionally set `WEATHER_LOCATIONS_JSON` to a JSON array of `{ "name", "latitude", "longitude" }` objects for multiple locations. Every 60 seconds means the system checks for new data every 60 seconds; it does not mean Open-Meteo generates a new observation every 60 seconds. Only a new `(station_id, observation_time, source)` row is stored. `observation_time`, `fetched_at`, and database `created_at` represent provider observation time, source-check time, and row creation time respectively. `WEATHER_MAX_AGE_SECONDS` defaults to 7200 seconds (two hours) to allow delayed model updates; READY requires a recent observation stored in the database, while STALE, UNAVAILABLE, and ERROR reflect actual stored data and the latest collection outcome. PostgreSQL remains authoritative; the `ml/datasets/weather/raw/` folder is reserved for future archive work and no duplicate CSV is currently written. No weather-derived processed features are fabricated. See `app/services/README.md` for configuration, migration, endpoint and verification details. Run one Uvicorn worker for this in-process scheduler; multiple workers would each poll.

The same startup worker checks the official public NWDP CKAN `datastore_search` API for CWC hourly telemetry every `HYDROLOGY_POLL_INTERVAL_SECONDS` (default 60). Defaults use verified resource IDs for Krishna-basin water level and Andhra Pradesh rainfall; override them with `NWDP_CWC_KRISHNA_WATER_LEVEL_RESOURCE_ID` and `NWDP_CWC_ANDHRA_RAINFALL_RESOURCE_ID`. No NWDP API key is configured because these verified resources are public. It fetches descending `_id` pages and persists only new rows; station/time duplicates are skipped. The source publishes hourly data, so a one-minute check does not mean a new reading every minute. Naive `Data Acquisition Time` values are interpreted using `NWDP_OBSERVATION_TIMEZONE` (default `Asia/Kolkata`); verify this assumption against the source if your selected resource uses another timezone. `observation_time` and `fetched_at` are stored separately. Water-level rows expose an `Is_DischargeDataAvailable` flag but no discharge measurement, so `discharge` remains null.

Authenticated hydrology endpoints are `GET /api/hydrology/status`, `/latest`, `/stations`, and `/observations`; `GET /api/data-readiness` reports weather, hydrology, GIS, model and feature readiness. The collector does not trigger predictions. Run one Uvicorn worker because collection is an in-process scheduled task.

For PostgreSQL, install the declared `psycopg` driver and set `DATABASE_URL` in `backend/.env`, for example:

```dotenv
DATABASE_URL=postgresql+psycopg://db_user:db_password@localhost:5432/disasterguard_db
```

Create the database and PostGIS extension, then apply the SQL files documented in `../database/README.md`. The backend currently falls back to SQLite when `DATABASE_URL` is unset and does not automatically apply PostGIS migrations. The SQL schemas are a separate baseline and must be kept aligned with the SQLAlchemy models.

## Run

```powershell
uvicorn app.main:app --reload
```

API: <http://127.0.0.1:8000>  
Interactive docs: <http://127.0.0.1:8000/docs>

## Routes

- `POST /api/auth/register` — create an account
- `POST /api/auth/login` — obtain a bearer token
- `GET /api/users/me` — current account
- `POST`, `GET /api/predictions` — create a risk estimate and view your history
- `POST /api/recommendations` — generate guidance from a prediction and optional simulation
- `GET`, `POST /api/alerts` — list or create alerts
- `POST`, `GET /api/simulations` — run and view saved Digital Twin scenarios
- `GET`, `POST /api/resources` — list or create resources
- `POST /api/resources/allocate` — allocate resource quantity
- `POST /api/resources/plan` — prioritize demands and reserve nearest matching stock
- `GET /api/gis/risk-points` — GeoJSON risk points from your predictions
- `GET /api/weather/latest` — latest cached Open-Meteo observation per configured location
- `GET /api/weather/status` — database-backed READY/STALE/UNAVAILABLE/ERROR state, observation/fetch times, and collector health
- `GET /api/hydrology/status` — NWDP source status, freshness, and collection counters
- `GET /api/hydrology/latest` — latest actual observation per station/source
- `GET /api/hydrology/stations` — normalized station list
- `GET /api/hydrology/observations` — observations, optionally filtered by station/source/time
- `GET /api/data-readiness` — actual source, feature, model and prediction readiness
- `GET /api/satellite/status` — authenticate the Copernicus OAuth client without returning the token
- `GET /api/satellite/search/sentinel-2` — search Sentinel-2 L2A catalog metadata
- `GET /api/satellite/search/sentinel-1` — search Sentinel-1 GRD catalog metadata
- `GET /api/satellite/image/{collection}` — request a bounded AOI TIFF (maximum 1024×1024 pixels)

Protected routes require the login token in the `Authorization: Bearer <token>` header.

After logging into the app, authorize these requests with `Authorization: Bearer <JWT>`:

```text
GET http://127.0.0.1:8000/api/satellite/status
GET http://127.0.0.1:8000/api/satellite/search/sentinel-2?latitude=16.5062&longitude=80.6480&start_date=2026-09-01&end_date=2026-09-20&cloud_coverage=30&limit=10
GET http://127.0.0.1:8000/api/satellite/search/sentinel-1?latitude=16.5062&longitude=80.6480&start_date=2026-09-01&end_date=2026-09-20&limit=10
```

The search routes return Catalog metadata, including product ID, collection, sensing time, bounding box and cloud coverage when supplied by the catalog; they do not expose OAuth tokens or raw asset download URLs. The image route uses Process API for a small area and returns TIFF bytes. Satellite-derived features are not yet generated or connected to the ML model.

Flood prediction uses the trained ML/SHAP pipeline only when a model artifact is available; other cases use a demonstrator weather heuristic. Digital Twin results are heuristic scenario estimates, not physical impact forecasts. No API result is an official emergency warning.

## Hydrology verification

Official datasets: [CWC River Water Level Telemetry Hourly](https://nwdp.nwic.gov.in/dataset/river-water-level-telemetry-hourly-central-water-commission-cwc) and [CWC Rainfall Telemetry Hourly](https://nwdp.nwic.gov.in/dataset/rainfall-cwc-telemetry-hourly). Their public CKAN API is `https://nwdp.nwic.gov.in/api/3/action/datastore_search`. The verified resources are hourly; current source observations may be stale even when the collector's last fetch is recent. No discharge value is inferred from the source's availability flag.

Check collector state after starting the backend:

```text
GET http://127.0.0.1:8000/api/hydrology/status
GET http://127.0.0.1:8000/api/hydrology/latest
GET http://127.0.0.1:8000/api/data-readiness
```

Run offline fixture tests from `backend/` with `python -m unittest discover -s tests -v`. The tests use synthetic fixtures only; they are not production telemetry. A live source smoke-test is required before claiming operational data readiness.