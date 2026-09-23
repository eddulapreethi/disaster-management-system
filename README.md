# DisasterGuard AI — Frontend

React + Vite frontend, rebuilt to match the project's target folder structure
(pages/, components/, services/, maps/), with React Router and real Leaflet map tiles.

## What's real vs. placeholder

| Feature | Status |
|---|---|
| Risk Prediction, Digital Twin | Calls the real FastAPI backend's `/predict` (trained XGBoost model + SHAP). Falls back to a local estimate if the backend is offline. |
| Risk Map | Real Leaflet map with OpenStreetMap tiles and real region coordinates. |
| Live weather (Dashboard) | **Real** integration with the free [Open-Meteo API](https://open-meteo.com) — no key needed. |
| Login / Register | **UI only.** Stores a fake session in `localStorage` via `services/authService.js`. There is no backend auth endpoint yet — wire this to `backend/app/api/auth.py` once it exists. |
| Alerts, Resource Allocation, Recommendations | Derived client-side from the same station risk data (`services/alertService.js`, rule-based estimates) — not from a real alerts/resource-optimization backend yet. |

## Structure

```
frontend/
├── public/
│   ├── images/
│   └── icons/
├── src/
│   ├── components/       # Navbar, Sidebar, RiskCard, AlertCard, WeatherCard, PredictionCard, Loading, Dashboard
│   ├── pages/             # Home, Login, Register, DashboardPage, RiskPrediction, RiskMap, Simulation, Recommendations, ResourceAllocation, Alerts
│   ├── services/          # api.js, predictionService.js, weatherService.js, alertService.js, authService.js, stationData.js
│   ├── maps/               # RiskMap.jsx (Leaflet), MapLayers.jsx
│   ├── styles/             # global.css, dashboard.css
│   ├── App.jsx             # routing + auth-gated layout
│   └── main.jsx
├── package.json
└── README.md
```

## Run it

```bash
npm install
cp .env.example .env
npm run dev        # http://localhost:5173
```

Start the backend first for real predictions (otherwise Risk Prediction/Simulation
silently fall back to an offline estimate — the header status pill shows which):

```bash
cd ../backend    # or wherever disasterguard-backend lives
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## Routes

| Route | Auth required | Page |
|---|---|---|
| `/` | No | Home |
| `/login`, `/register` | No | Login, Register |
| `/dashboard` | Yes | Overview + live weather |
| `/risk-prediction` | Yes | Model-backed prediction with SHAP |
| `/risk-map` | Yes | Leaflet map |
| `/simulation` | Yes | Digital twin what-if scenarios |
| `/recommendations` | Yes | AI guidance + chat |
| `/resource-allocation` | Yes | Suggested resource levels |
| `/alerts` | Yes | Auto-generated alerts |

"Auth required" here just means: not logged in → redirected to `/login`. Since auth is
UI-only, any email/password combination works.

## Build for production

```bash
npm run build     # outputs to dist/
```
