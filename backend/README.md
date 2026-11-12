# DisasterGuard AI Backend

FastAPI backend for the DisasterGuard AI frontend. Bearer-token authentication protects application APIs. Incident review uses a reviewer role assigned only by an offline administrative command; no public role-management endpoint exists.

## Setup (Windows)

From the project directory:

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create `.env` with a long random `JWT_SECRET_KEY`. A trained flood-model artifact is not currently included. `GET /api/data-readiness` validates the configured model artifact, feature manifest, and runtime feature path rather than relying on file presence. The current 20-feature schema has no verified units/source mapping, and runtime weather/hydrology does not produce those features; see `../ml/README.md` for the measured data gaps and training requirements. Do not interpret the current demonstrator heuristic as a calibrated probability or forecast.

### Local database files

The default SQLite database is `backend/disasterguard.db`. Relative SQLite paths in `DATABASE_URL` (including the example `sqlite:///./disasterguard.db`) are resolved from the backend directory, so starting the API from a different working directory will still use the same database. Keep local database files and `.env` out of source control. Any older database copies are kept separately under `backend/data/legacy/` and are not used by the application.

### Community incident reporting

The authenticated incident-report API is separate from the environmental observation catalog and saved prediction/risk map:

- `POST /api/incidents` creates a `pending` report. The API records `source=community_report`, submission time, reporter ownership, incident time and its IANA timezone, WGS 84 point, and optional evidence metadata. Incident time must be a valid local time in the supplied zone or include a matching UTC offset. Ambiguous/nonexistent daylight-saving times are rejected.
- `GET /api/incidents` supports `hazard_category`, `verification_status`, timezone-aware `start_time`/`end_time`, WGS 84 bbox (including antimeridian crossing), and bounded offset pagination. Signed-in users see report descriptions with reporter identity and evidence metadata withheld. Rejected reports are visible only to their reporter and reviewers.
- `GET /api/incidents/analytics` returns descriptive counts by hazard, review status, and UTC day. No country/region breakdown is claimed: verified administrative-area attribution is not available.
- `GET /api/incidents/{id}` exposes evidence metadata and review history only to the report owner or a reviewer.
- `PATCH /api/incidents/{id}` permits the owner to edit an eligible pending/needs-review report; clients cannot change verification status.
- `POST /api/incidents/{id}/reviews` is reviewer-only. Reviewers cannot review their own submissions. Decisions are recorded with reviewer ID/name, time, status transition, and a required note for rejection/needs-review. Review history has no edit/delete API.

Incident categories are flood, cyclone, storm, wildfire, heatwave, drought, earthquake, landslide, and other. Submitted titles/descriptions are visible to signed-in users; the UI instructs reporters not to include personal/contact details. Reporter identity and evidence metadata are not part of global map/list responses. Evidence handling is metadata-only: no file upload, URL fetch, or evidence storage/scanning is implemented. Reports are community submissions, never official observations or emergency warnings. Empty results do not imply that no disaster exists.

Legacy rows in the existing `disasters` table have no reporter owner and are deliberately excluded from incident APIs and analytics; they are preserved, not assigned to a fabricated owner. SQLite startup applies additive incident columns and the new review table. Back up the database before deployment. PostgreSQL deployments must apply `database/migrations/005_incident_reporting.sql` with the approved database migration procedure before starting the updated backend; schema changes are additive, and the migration is not automatically run for PostgreSQL.

Create a reviewer account using the normal registration flow, then grant reviewer access from the `backend` directory using a local administrative shell:

```powershell
python -m app.scripts.provision_reviewer reviewer@example.org
```

The command promotes an existing account in the database selected by `DATABASE_URL`; it does not print credentials or provide self-service escalation. Restrict command/database access to trusted administrators.

Incident reporting uses public/authenticated user-submitted information with no automatic source verification. Status `verified` means a reviewer made an application review decision; it is not confirmation by an official agency.

### General-purpose assistant

The assistant sends ordinary open-ended questions to Ollama's OpenAI-compatible chat-completions API using `qwen2.5:3b`. It does not train a model or fall back to a cloud provider. The model must be installed and running on the same machine as the backend when using `localhost`; for Docker or a backend on another machine, set `DISASTERGUARD_ASSISTANT_BASE_URL` to a reachable Ollama address instead.

```dotenv
DISASTERGUARD_ASSISTANT_PROVIDER=ollama
DISASTERGUARD_ASSISTANT_BASE_URL=http://localhost:11434/v1
DISASTERGUARD_ASSISTANT_MODEL=qwen2.5:3b
DISASTERGUARD_ASSISTANT_TIMEOUT_SECONDS=120
```

Install Ollama for Windows from <https://ollama.com/download/windows>, then open PowerShell and run the local checks and model:

```powershell
ollama --version
ollama list
ollama run qwen2.5:3b
```

Ollama must remain running while the backend uses it; the Windows Ollama application normally provides the local service. `ollama run` downloads the model if needed. The backend checks the configured Ollama `/api/tags` endpoint before generation and reports when Ollama is unreachable or the model is not installed. No API key or billing is needed. The configured Ollama URL is the only target: failures return an error and never trigger cloud failover. Never put provider credentials in frontend code or commit a populated `.env`. Restart the backend after changing `.env`.

The backend supplies at most the eight latest validated user/assistant history messages. For project capability questions, it retrieves a small set of relevant passages from an allowlist of local repository Markdown files and supplies those as evidence to the model. Responses are kept concise by default and capped at 512 tokens; the request asks Ollama to keep the configured model loaded for ten minutes to reduce cold-start delays between questions. These settings do not change the configured model or guarantee fast inference on CPU-only hardware. Weather, hydrology, readiness, saved predictions, and historical comparisons continue to use backend services and stored records rather than model guesses. A request for a location-specific current flood risk reports matching stored observations, if any, and explicitly distinguishes those observations from a prediction. No web-search integration is configured, so provider output is not live research and is returned without fabricated citations. If Ollama is unavailable or generation fails, the API returns a safe, actionable error rather than treating failed generation as a successful answer. `DISASTERGUARD_ASSISTANT_TIMEOUT_SECONDS` configures the model response timeout (default 120 seconds); the frontend allows 125 seconds for the full request. The authenticated `GET /api/assistant/status` endpoint reports Ollama reachability and whether the configured model is installed.

All persisted observation datetimes are UTC. SQLite does not retain timezone metadata in `DateTime(timezone=True)` columns, so API serializers explicitly treat naive database values as UTC and emit ISO timestamps with a `Z` suffix; browsers must not interpret stored UTC as local time. Freshness is based on the provider's `observation_time`, not `fetched_at`; observations more than five minutes in the future are reported as errors.

The flood prediction endpoint returns HTTP 503 until both a validated trained artifact and a verified runtime feature builder exist. It does not save the former weather heuristic as a flood prediction. Existing saved prediction rows are legacy/unverified and are displayed as history only; they are not validated forecasts. Current ML statuses remain `NOT_READY`: the included EM-DAT records have no matching environmental inputs or suitable continuous flood target, and the existing 20-factor feature definitions remain unverified. The frontend and API must not present the weather heuristic as a flood prediction.

### Global locations and provider coverage

The shared location contract accepts valid WGS 84 coordinates anywhere on Earth; selecting a coordinate does not imply provider, GIS, hydrology, or prediction coverage. Authenticated `GET /api/coverage?latitude=...&longitude=...` reports configured source scope independently for weather, hydrology, Kochi reference GIS, and flood, wildfire, storm, cyclone, heatwave, drought, and other prediction categories. `SUPPORTED` for local GIS refers only to the Kochi reference-layer extent, `UNVERIFIED` hydrology means no verified station-to-point mapping, and all listed hazard predictions remain `UNAVAILABLE` as validated operational coverage. In particular, flood readiness remains `NOT_READY`; the unvalidated wildfire/storm demonstrator heuristics are not verified coverage. Open-Meteo on-demand weather responses include provider provenance and metadata; new weather and hydrology observations preserve provider metadata in JSON. Rows collected before the metadata addition receive an empty object, not reconstructed metadata. Provider access or prediction coverage must not be inferred beyond the returned scope/status.

Observation tables include an additive JSON `provider_metadata` column. SQLite adds missing columns at startup without deleting rows; apply `database/migrations/004_provider_metadata.sql` to existing PostgreSQL databases before deploying this version. New databases include the columns automatically.

Authenticated `GET /api/environmental-data` provides a read-only catalog over stored weather and hydrology. It supports provider/category, timezone-aware time, geographic bounds (including antimeridian-crossing bounds), coordinate-radius filters, and bounded offset pagination (`limit` 1–1000, `offset` 0–10000, with `has_more`). Application disaster reports are withheld because the existing table has no creator ownership or visibility policy; their descriptions must not be assumed public. The response keeps weather and hydrology separate and reports unpersisted forecasts/satellite metadata and regional GIS separately. Missing values stay null, non-finite numeric values are represented as strings with quality findings, and query-time checks do not modify stored rows. This endpoint makes no live provider calls: no matching record means no matching stored data, not proof of provider outage or provider-wide unavailability. See `../docs/PHASE_2_7_GLOBAL_ENVIRONMENTAL_DATA_FOUNDATION.md` for exact field and status semantics.

The current environmental-data and satellite response fields, status meanings, error responses, pagination rules, and consumer migration notes are documented in `../docs/PHASE_2_14_API_CONTRACT_AND_CONSUMER_COMPATIBILITY.md`. No public API versioning policy is defined; the document describes the current implementation rather than promising a versioned compatibility guarantee.

The frontend calls `http://localhost:8000/api/assistant/chat` by default. For Docker on Windows, the backend can often reach Ollama at `http://host.docker.internal:11434/v1`; otherwise configure the reachable Ollama address for your deployment. Set `VITE_API_BASE` if the backend is not at its default URL.

Provider failures are reported separately for unavailable Ollama, a model not installed locally, unsupported requests, timeouts, and invalid responses. Backend diagnostics log only the failure class.

Assistant unit tests mock Ollama responses and do not make network or paid API calls. To opt into the local-model smoke test after installing the model and starting Ollama, set `$env:DISASTERGUARD_RUN_ASSISTANT_INTEGRATION='1'` in the backend PowerShell session and run `python -m pytest tests/test_assistant_provider.py -q`; leave it unset for routine offline tests.

### Copernicus Sentinel access

Create a server-side OAuth client in the Copernicus Data Space dashboard under **User Settings → OAuth clients**. Add its values to local `backend/.env` as `COPERNICUS_CLIENT_ID` and `COPERNICUS_CLIENT_SECRET`; never put them in React or commit the `.env` file. `backend/.env.example` contains empty placeholders only. The backend caches the OAuth token and uses the official Sentinel Hub Catalog and Process APIs. No satellite data is available until a valid client is configured and authorized.

From the repository root, run the one-shot, sanitized OAuth and read-only Catalog diagnostic in PowerShell:

```powershell
python backend\scripts\copernicus_auth_diagnostic.py
```

The script uses the backend package's existing `.env` loader, makes at most one token request and one Catalog request (only after successful token acquisition), and never prints credentials or tokens. Token HTTP status diagnoses OAuth client authentication; a successful token followed by Catalog HTTP 401/403 indicates a Catalog authorization/request issue. Both HTTP statuses must be successful to confirm live Catalog access. A successful Catalog response with zero features still means the request was accepted, but no matching scenes were found in the script's small Kochi-area, recent-date query; it does not prove broad coverage, image processing, or flood-detection capability. Automated tests mock all responses and make no external requests.

To verify Process API access yourself, run this bounded read-only test from the repository root in PowerShell:

```powershell
python backend\scripts\copernicus_process_diagnostic.py --latitude 9.9312 --longitude 76.2673 --width 64 --height 64 --read-timeout 120
```

The sample point can be replaced with any valid WGS 84 point; a bbox can be supplied instead with `--bbox WEST SOUTH EAST NORTH` (maximum 0.25 degrees per dimension). The diagnostic uses the last 30 UTC days by default; `--start-date`, `--end-date`, `--cloud-coverage`, `--width`, `--height`, `--connect-timeout`, `--read-timeout` and `--output-dir` are optional. It makes one OAuth request, one Catalog query and at most one Process API request (it disables the backend service's normal one-time 401 retry for this diagnostic), limits image dimensions to 1024 pixels, and defaults to a 128×128 request. Separate `COPERNICUS_CONNECT_TIMEOUT_SECONDS` (default 5) and `COPERNICUS_READ_TIMEOUT_SECONDS` (default 90) settings are also supported in `backend/.env`; read timeout is the maximum wait for response data, not a total request deadline. The diagnostic reports connection and read timeouts separately and does not report timeout as success. A valid TIFF is saved under a newly created temporary directory unless `--output-dir` is supplied. The script reports statuses, Catalog item ID/acquisition time, content type, TIFF validity and dimensions without printing credentials, tokens, authorization headers, or response bodies. Catalog selection does not pin the Process API output to that specific item; the Process API selects imagery by AOI/time and may stitch data. See `../docs/PHASE_2_11_SENTINEL_PROCESS_LIVE_VERIFICATION.md`. Tests are mocked and make no external requests.

On backend startup, an asynchronous background worker fetches Open-Meteo current conditions immediately and polls every `WEATHER_POLL_INTERVAL_SECONDS` (default 300 seconds). Configure one study location with `WEATHER_LOCATION_NAME`, `WEATHER_LATITUDE`, and `WEATHER_LONGITUDE`; optionally set `WEATHER_LOCATIONS_JSON` to a JSON array of `{ "name", "latitude", "longitude" }` objects for multiple locations. Every five minutes means the system checks for new data every five minutes; it does not mean Open-Meteo generates a new observation every five minutes. Only a new `(station_id, observation_time, source)` row is stored. `observation_time`, `fetched_at`, and database `created_at` represent provider observation time, source response fetch time, and row creation time respectively. Stored coordinates are the configured/requested location; the on-demand response also exposes Open-Meteo's resolved grid coordinates, which may differ. `WEATHER_MAX_AGE_SECONDS` defaults to 7200 seconds (two hours). API freshness is based on `observation_time`; collection status is reported separately from freshness, and required-measurement availability is also explicit. The on-demand `/api/weather/current` response includes requested and resolved coordinates, units, provider observation time, backend fetch time, and freshness status; stale values are marked stale and are not used to create an estimate. SQLite is the current default runtime database unless `DATABASE_URL` is configured. No weather-derived processed features are fabricated. See `app/services/README.md` for configuration, migration, endpoint and verification details. Run one Uvicorn worker for this in-process scheduler; multiple workers would each poll.

Location search uses the public Open-Meteo geocoding API, not a hardcoded list. It supports city, town, village, district, state and country names, with strong coverage in India and other geocoded regions. The frontend queries `GET /api/geocoding/search?query=Hyderabad&limit=8`; the API returns canonical names, coordinates, administrative metadata, and a `display_name` suitable for selection. No API key is required for the public endpoint, and coverage remains provider-dependent rather than guaranteed worldwide.

The same startup worker checks the public NWDP CKAN `datastore_search` API for CWC hourly telemetry every `HYDROLOGY_POLL_INTERVAL_SECONDS` (default 300). Defaults use the resource IDs for Krishna-basin water level and Andhra Pradesh rainfall; override them with `NWDP_CWC_KRISHNA_WATER_LEVEL_RESOURCE_ID` and `NWDP_CWC_ANDHRA_RAINFALL_RESOURCE_ID`. No NWDP API key is required for these public resources. It fetches descending `_id` pages and persists only new rows; station/time duplicates are skipped. Five-minute polling does not make old provider telemetry fresh. Readiness reports collection status separately from observation freshness, observation and fetch timestamps, age, reported station/location metadata, units, scanned/valid/inserted counts, duplicate and parser counts, and whether an observation newer than the stored maximum was found. The source rows do not provide an official station ID; `station_id` is an internal deduplication key derived from available station metadata and must not be interpreted as a source-issued identifier. No water-level datum or danger threshold is inferred. Per-source freshness thresholds can be configured with `HYDROLOGY_CWC_KRISHNA_WATER_LEVEL_STALE_AFTER_HOURS` and `HYDROLOGY_CWC_ANDHRA_RAINFALL_STALE_AFTER_HOURS`; the global default remains six hours. Naive `Data Acquisition Time` values are interpreted using `NWDP_OBSERVATION_TIMEZONE` (default `Asia/Kolkata`); verify this assumption against the source if your selected resource uses another timezone. `observation_time` and `fetched_at` are stored separately. Water-level rows expose an `Is_DischargeDataAvailable` flag but no discharge measurement, so `discharge` remains null.

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
- `GET /api/alerts` — list generated in-app estimate alerts
- `POST`, `GET /api/simulations` — run and view saved Digital Twin scenarios
- `GET`, `POST /api/resources` — list or create inventory
- `PATCH`, `DELETE /api/resources/{resource_id}` — edit or remove inventory
- `POST /api/resources/allocate` — allocate resource quantity
- `POST /api/resources/plan` — prioritize demands and reserve nearest matching stock
- `GET /api/gis/risk-points` — GeoJSON risk points from your predictions
- `GET /api/geocoding/search?query=Hyderabad&limit=8` — provider-backed location search by city, district, state, or country; returns canonical names, coordinates, and admin metadata
- `GET /api/weather/latest` — latest cached Open-Meteo observation per configured location
- `GET /api/weather/current?latitude=...&longitude=...` — on-demand Open-Meteo response with requested/resolved location, units, observation/fetch times, and freshness
- `GET /api/weather/status` — stored observation freshness and measurement availability separate from collection status
- `GET /api/hydrology/status` — NWDP source status, freshness, and collection counters
- `GET /api/hydrology/latest` — latest actual observation per station/source
- `GET /api/hydrology/stations` — normalized station list
- `GET /api/hydrology/observations` — observations, optionally filtered by station/source/time
- `GET /api/data-readiness` — actual source, feature, model and prediction readiness
- `GET /api/satellite/status` — authenticate the Copernicus OAuth client without returning the token
- `GET /api/satellite/search/sentinel-2` — search Sentinel-2 L2A catalog metadata
- `GET /api/satellite/search/sentinel-1` — search Sentinel-1 GRD catalog metadata
- `GET /api/satellite/image/{collection}` — request a bounded AOI TIFF (maximum 1024×1024 pixels)
- `GET /api/satellite/scene/sentinel-2` — select a Catalog scene and request a bounded Sentinel-2 L2A TIFF

Hydrology `collection_status` distinguishes successful new rows, unchanged IDs, empty provider responses, duplicate-only responses, parse errors and provider errors. `freshness_status` is separate and always uses the source observation time, never the fetch time. See `../docs/HYDROLOGY_FRESHNESS_DIAGNOSTICS.md` for a live read-only source check and the known stale-data limitation.

The backend `POST`/`GET /api/simulations` workflow is a persisted, deterministic weather-based what-if estimate, not a physically calibrated model. It is separate from the React Stage 1 Digital Twin, which runs a local illustrative scenario and does not call the simulation API or persist results. The risk-prediction UI fetches current weather on demand from `/api/weather/current` and submits its measurements with the selected coordinates to `/api/predictions`; it does not submit a stored weather observation ID. Flood requests remain gated with HTTP 503 until a validated model and runtime feature builder are available. Any enabled weather heuristic is demonstrator-only, not a calibrated probability or warning. In-app estimate alerts use `ALERT_MINIMUM_SCORE` (default `30`) and suppress the same user's same-hazard/severity/location repeat for `ALERT_DEDUPLICATION_SECONDS` (default `1800`). Alerts are not official warnings; no external delivery is configured, and the alert API is read-only to prevent arbitrary user-submitted warnings.

Resource inventory supports list/create/edit/delete. Direct and planned stock changes use conditional database updates; a plan rolls back all reservations if any item no longer has the planned stock. Demand priority is a caller-provided 0–100 planning score, not an automatically verified impact assessment. Pickup ordering is straight-line distance only.

Protected routes require the login token in the `Authorization: Bearer <token>` header.

After logging into the app, authorize these requests with `Authorization: Bearer <JWT>`:

```text
GET http://127.0.0.1:8000/api/satellite/status
GET http://127.0.0.1:8000/api/satellite/search/sentinel-2?latitude=16.5062&longitude=80.6480&start_date=2026-09-01&end_date=2026-09-20&cloud_coverage=30&limit=10
GET http://127.0.0.1:8000/api/satellite/search/sentinel-1?latitude=16.5062&longitude=80.6480&start_date=2026-09-01&end_date=2026-09-20&limit=10
```

The search routes return Catalog metadata, including product ID, collection, sensing time, bounding box and cloud coverage when supplied by the catalog; they do not expose OAuth tokens or raw asset download URLs. The image route uses Process API for a small area and returns TIFF bytes. The Sentinel-2 scene route requires either a complete WGS 84 point or bbox plus an inclusive date range. It searches at most 20 Catalog results, applies the optional scene cloud-coverage filter, chooses a usable result, then requests a three-band B04/B03/B02 UINT16 DN TIFF. The Process API request is limited to 1024×1024 pixels and a bbox no larger than 0.25 degrees in either dimension; a point query requests a small neighborhood. The response is a TIFF attachment with URL-encoded `X-Satellite-Metadata` and separate acquisition, Catalog-fetch, Process-request, and download timestamps. Cloud percentage is scene metadata, not necessarily cloudiness over every pixel in the requested AOI.

The Process API is time/AOI based and does not pin a Catalog item ID; the response explicitly labels this as `TIME_AND_AOI_MATCHED_NOT_ITEM_PINNED`. The Catalog item is the selected temporal/AOI reference, not proof that every returned pixel came from that exact item. The Phase 2.11A standalone diagnostic was reported to have received a valid 64×64 TIFF; this verifies provider access from that local diagnostic only, not the authenticated application endpoint. The React risk-prediction screen now offers a bounded 64×64 scene retrieval and TIFF download, with acquisition, Catalog-fetch, Process-request, and download times kept distinct. Process output is streamed with a 16 MiB cap; the scene endpoint validates readable TIFF structure, georeferencing tags, and requested dimensions before returning it. The application route and frontend contract are tested with mocked provider/API responses; do not infer that the application endpoint has been live-verified from the diagnostic result. The TIFF is not a confirmed disaster observation or flood extent, and no satellite-derived feature is connected to the ML model. Separate `COPERNICUS_CONNECT_TIMEOUT_SECONDS` (default 5) and `COPERNICUS_READ_TIMEOUT_SECONDS` (default 90) settings configure backend OAuth, Catalog, and Process requests; the frontend allows 120 seconds for the bounded image request. See `../docs/PHASE_2_10_SENTINEL_SATELLITE_IMAGERY_INTEGRATION.md` and `../docs/PHASE_2_11_SENTINEL_PROCESS_LIVE_VERIFICATION.md` for contract and limitations.

Flood ML inference rejects arbitrary client-supplied feature vectors until a validated feature-source mapping is implemented. `POST /api/predictions` accepts `disaster_type`, `latitude`, `longitude`, `rainfall_mm`, `temperature_c`, and `wind_speed_kmh`; optional `features` are not usable for flood inference, and unknown fields (including `weather_observation_id`) are rejected. The current UI fetches on-demand current weather for the selected coordinates and submits those measurements with the coordinates; the backend does not associate them with a persisted observation. Flood requests return HTTP 503 without scoring or saving until model readiness passes. A successful non-flood heuristic response contains a `prediction` record (`id`, hazard type, coordinates, weather inputs, score, level, creation time), recommendations, `model_source`, model/target metadata, `input_provenance`, `risk_band`, explanation, top contributions, and `alert_generated`. The UI currently requests flood only, so it receives the readiness 503 rather than that success response. Heuristic scores are not calibrated probabilities, hazard thresholds, or forecasts. React Stage 1 Digital Twin scenarios remain local-only; the separate backend simulations API does not drive that page. No API result is an official emergency warning.

Heuristic risk-level software cutoffs are low `<30`, moderate `30–<60`, high `60–<80`, and critical `≥80`; the API display `risk_band` and frontend colors use low `<30`, medium `30–<60`, and high `≥60`. These are unvalidated demonstrator categories, not scientifically calibrated or official hazard thresholds.

## Hydrology verification

Official datasets: [CWC River Water Level Telemetry Hourly](https://nwdp.nwic.gov.in/dataset/river-water-level-telemetry-hourly-central-water-commission-cwc) and [CWC Rainfall Telemetry Hourly](https://nwdp.nwic.gov.in/dataset/rainfall-cwc-telemetry-hourly). Their public CKAN API is `https://nwdp.nwic.gov.in/api/3/action/datastore_search`. The verified resources are hourly; current source observations may be stale even when the collector's last fetch is recent. No discharge value is inferred from the source's availability flag.

Check collector state after starting the backend:

```text
GET http://127.0.0.1:8000/api/hydrology/status
GET http://127.0.0.1:8000/api/hydrology/latest
GET http://127.0.0.1:8000/api/data-readiness
```

Run offline fixture tests from `backend/` with `python -m unittest discover -s tests -v`. The tests use synthetic fixtures only; they are not production telemetry. A live source smoke-test is required before claiming operational data readiness.