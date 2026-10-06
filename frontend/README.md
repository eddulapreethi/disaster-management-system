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

The application has no role-based user system. Login and registration use the backend's ordinary user account endpoints; the returned bearer token is stored in browser `localStorage` and sent with protected API requests.

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

The frontend reads `VITE_API_BASE` and defaults to `http://localhost:8000`. Create a local `.env` file in this directory to override it:

```dotenv
VITE_API_BASE=http://localhost:8000
```

The shared API client checks the backend root and prefixes feature requests with `/api`. Predictions send coordinates, current Open-Meteo weather and the flood-model feature values to `/api/predictions`. A trained artifact configured with `DISASTERGUARD_MODEL_PATH` enables model+SHAP inference; otherwise the backend returns an explicitly labeled weather heuristic. Network failures can use an offline demonstration estimate, which is not persisted and has no SHAP factors. The risk map and alerts read the signed-in user's saved backend records; simulation results and resource plans also use backend APIs.

The backend polls Open-Meteo and public NWDP/CWC telemetry on configurable schedules and stores observations; the dashboard displays a data-readiness panel with observation/fetch times and stale/unavailable states. CWC water-level and rainfall sources are hourly, so polling every minute does not guarantee a new measurement every time. Satellite search is available in the backend but is not yet displayed in the React UI. Licensed training datasets, a trained production model, PostGIS runtime deployment, and external SMS/email/push delivery are not included yet. The assistant uses deterministic guidance rules, not a generative AI service.

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

