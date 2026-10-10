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
- DisasterGuard assistant

Supported product features include saved risk estimates, risk-map visualization, what-if simulations, preparedness recommendations, alerts, and resource planning/allocation. Exact readiness and enabled capabilities depend on the backend configuration and available model/data sources.

The application has no role-based user system. Login and registration use the backend's ordinary user account endpoints; the returned bearer token is stored in browser `localStorage` and sent with protected API requests.

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
```

## Backend URL

The assistant sends chat requests to `http://localhost:8000/api/assistant/chat` by default. The frontend reads `VITE_API_BASE` and defaults to `http://localhost:8000`. Create a local `.env` file in this directory to override it:

```dotenv
VITE_API_BASE=http://localhost:8000
```

The shared API client checks the backend root and prefixes feature requests with `/api`. Predictions send coordinates, current Open-Meteo weather and the flood-model feature values to `/api/predictions`. A trained artifact configured with `DISASTERGUARD_MODEL_PATH` enables model+SHAP inference; otherwise the backend returns an explicitly labeled weather heuristic. Network failures can use an offline demonstration estimate, which is not persisted and has no SHAP factors. The risk map and alerts read the signed-in user's saved backend records; simulation results and resource plans also use backend APIs.

The backend polls Open-Meteo and public NWDP/CWC telemetry on configurable schedules and stores observations; the dashboard displays a data-readiness panel with observation/fetch times and stale/unavailable states. CWC water-level and rainfall sources are hourly, so polling every minute does not guarantee a new measurement every time. Satellite search is available in the backend but is not yet displayed in the React UI. Licensed, aligned flood training data, a trained model artifact, PostGIS runtime deployment, and external SMS/email/push delivery are not included yet.

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
