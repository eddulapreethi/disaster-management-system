# DisasterGuard AI Frontend

This directory contains the React web interface for DisasterGuard AI. It provides the screens and visual controls for dashboard review, risk prediction, maps, scenario simulation, recommendations, resource allocation and alerts.

## Frontend Stack

- React 18
- React Router 6
- Vite 5
- Leaflet and React Leaflet

## Main Screens

- Home, login and registration
- Dashboard
- Risk prediction
- Risk map
- What-if simulation
- Recommendations
- Resource allocation
- Alerts
- Community incident reports and situational-awareness map
- DisasterGuard assistant

Supported product features include saved risk estimates, risk-map visualization, what-if simulations, preparedness recommendations, alerts, and resource planning/allocation. Exact readiness and enabled capabilities depend on the backend configuration and available model/data sources.

Login and registration use the backend's bearer-token account endpoints; the returned token is stored in browser `localStorage` and sent with protected API requests. Incident reviewer permissions are assigned offline to an existing account; ordinary users cannot promote themselves.

Inventory supports create, edit, remove and list operations; resource plans reserve persisted stock and report shortages. Alert cards display persisted API fields and explicitly label automated estimates as not official warnings. Alert listing is read-only. Scenario runs require all three weather measurements and will not substitute defaults when the data is incomplete.

The authenticated `/incidents` screen supports WGS 84 community report submission, owner edits while a report remains eligible, review actions for offline-provisioned reviewers, status/date/hazard filters, a separate global report map, and descriptive counts. Map/list entries omit reporter identity and evidence details; private evidence metadata and review history are available only to the owner or a reviewer. Reports are user submissions, not official observations or warnings. The interface does not upload evidence files, infer country/region from coordinates, or send verified-incident notifications. An empty map/result is not evidence that no hazard exists.

The authenticated assistant at `/assistant` sends ordinary questions to the configured Ollama `qwen2.5:3b` model through its OpenAI-compatible API; failures never fall back to a cloud provider. Follow-up context is limited to the latest eight user/assistant messages. Questions about documented project capabilities can include relevant passages retrieved from repository documentation; saved predictions, readiness, weather and hydrology questions use backend services and stored records instead of model guesses. The assistant has no general web-search integration, so it does not claim live external research. Its chat request allows up to 125 seconds for local inference; other API calls keep the standard 8-second timeout. Backend health and configured model availability are available through authenticated `GET /api/assistant/status`.

## Run Locally

Install Node.js and npm, then run these commands from this directory:

```powershell
npm install
npm run dev
```

Vite serves the frontend at <http://localhost:5173>. To create and preview a production build:

```powershell
npm run build
npm run preview
npm test
```

## Backend URL

The assistant sends chat requests to `http://localhost:8000/api/assistant/chat` by default. The frontend reads `VITE_API_BASE` and defaults to `http://localhost:8000`. Create a local `.env` file in this directory to override it:

```dotenv
VITE_API_BASE=http://localhost:8000
```

The shared API client checks the backend root and prefixes feature requests with `/api`. The risk-prediction screen fetches current Open-Meteo weather on demand for the selected coordinates through `/api/weather/current`, then submits `disaster_type`, `latitude`, `longitude`, `rainfall_mm`, `temperature_c`, and `wind_speed_kmh` to `/api/predictions`. It does not send a stored observation ID, and the prediction request does not claim database provenance for those values. The current screen requests a flood prediction, which remains HTTP 503 until the validated model and runtime feature pipeline are ready; it does not save a heuristic flood score. Successful non-flood heuristic API responses contain the saved prediction, recommendations, model source, heuristic risk band, explanation, and client-supplied input provenance; those results are demonstrator-only, not calibrated probabilities or forecasts. See `../ml/README.md` for current model readiness and required training data. The risk map and alerts read the signed-in user's saved backend records, and resource plans use backend APIs.

The React Digital Twin Stage 1 page runs deterministic illustrative scenarios locally within the Kochi study area; it does not call an API or persist its scenarios. The backend `/api/simulations` endpoints are a separate persisted, weather-based what-if workflow and are not used by that page. Stage 1 results are not physical impact forecasts and are not passed to recommendations.

Frontend risk bands and colors follow the backend heuristic `risk_band` cutoffs: low `<30`, medium `30–<60`, and high `≥60`. Backend `risk_level` further distinguishes high (`60–<80`) from critical (`≥80`). These software categories are not scientifically calibrated or official hazard thresholds.

The risk-prediction page uses one selected-location state for its search, map point, browser location, prediction request, and weather display; the dashboard weather panel uses that same selection. Browser geolocation is requested only after **Use my current location** is clicked. Search uses the existing authenticated backend Open-Meteo geocoding route. A map click selects coordinates only and does not infer a place name or gauge. Weather is requested for those selected coordinates, but provider availability and flood-model readiness are separate. Packaged reference GIS overlays cover the Kochi study area only; they are not nationwide GIS or hydrology coverage. Dashboard NWDP/CWC observations are shown with their source station and are not substituted for the selected place's weather.

The shared location starts unselected and accepts valid coordinates anywhere on Earth. Place name, country, region, and provider metadata are optional; map selection remains coordinate-only. The location selector map opens at a world view, independently of Kochi-only overlays. Its source-coverage panel calls authenticated `/api/coverage` and distinguishes supported, unsupported, stale, unavailable, and unverified capabilities. A fresh on-demand weather response supports that point request only; it does not establish hydrology or hazard coverage. Flood prediction remains unavailable with HTTP 503 while backend readiness is `NOT_READY`.

The backend polls Open-Meteo and public NWDP/CWC telemetry on configurable schedules and stores observations. Weather distinguishes the provider observation timestamp from the backend fetch timestamp, displays requested and provider-resolved coordinates, and marks data stale outside the configured freshness window. Collection status and observation freshness are separate. Hydrology readiness displays source/station metadata, observation and fetch timestamps, units, and freshness; its internal station keys are not official CWC station IDs. Missing hydrology values remain unavailable rather than being shown as zero. CWC water-level and rainfall sources are hourly, so polling every few minutes does not guarantee a new measurement every time. The configured hydrology sources cover their own reported Krishna-basin/Andhra Pradesh stations, not Kochi or arbitrary selected locations. The risk-prediction screen can request a bounded Sentinel-2 L2A TIFF for the selected coordinates and download it; it displays Catalog acquisition time separately from Catalog fetch, Process request, and image receipt times. It does not preview or interpret the TIFF, and explicitly warns that Process API output is not pinned to the displayed Catalog item and is not a live hazard observation or flood extent. A successful standalone provider diagnostic does not establish that the application's authenticated route works against live services; automated application tests are mocked. Licensed, aligned flood training data, a trained model artifact, PostGIS runtime deployment, and external SMS/email/push delivery are not included yet.

The Sentinel-2 image request is bounded to 64×64 pixels in the UI and uses the backend's configured `COPERNICUS_CONNECT_TIMEOUT_SECONDS` (default 5) and `COPERNICUS_READ_TIMEOUT_SECONDS` (default 90); the frontend request timeout is 120 seconds. These are connect/read timeouts, not a guaranteed total end-to-end deadline. Copernicus credentials remain backend-only.

The frontend validates environmental-data pagination and page-scoped counts before displaying or appending records. It uses the current environmental-data and satellite contracts documented in `../docs/PHASE_2_14_API_CONTRACT_AND_CONSUMER_COMPATIBILITY.md`; a malformed or duplicate environmental page is shown as an error rather than silently appended.

The frontend unit tests use Node's built-in test runner (`node --test`) and cover API alert-field presentation, location selection, weather freshness/provenance, changed-coordinate requests, and out-of-order request protection; they are not browser-driven end-to-end tests.

## Frontend Layout

```text
src/
  components/  Shared navigation, cards and UI components
  maps/        Leaflet map components
  pages/       Route-level screens
  services/    API client and frontend data/auth helpers
  styles/      Global and dashboard styles
  App.jsx      Routes and application layout
  main.jsx     React entry point
```
