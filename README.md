# 🌍 DisasterGuard AI

## AI-Powered Disaster Prediction & Decision Support System

DisasterGuard AI is an academic disaster-management demonstration that integrates weather, hydrological, historical, satellite and GIS data with a web application for data readiness, illustrative risk estimates, mapping, scenario simulation, recommendations, resource planning and in-app alerts.

> **Readiness notice:** Flood prediction is currently disabled (the API returns HTTP 503) because there is no compatible trained artifact, verified feature-source mapping or runtime feature builder. Existing scores are unverified history; heuristic estimates and Digital Twin scenarios are not validated forecasts or official warnings. See [`docs/PROJECT_COMPLETION_STATUS.md`](./docs/PROJECT_COMPLETION_STATUS.md).

---

## ✨ Feature status

| Area | Submission status |
|---|---|
| Accounts and protected pages | Bearer-token authentication. Incident review access is assigned to existing accounts by an offline administrator command; there is no self-service role change. |
| Weather | On-demand Open-Meteo current weather and a configurable background collector. This is model-derived weather, not a local sensor. Collection is limited to configured locations; coordinate acceptance does not prove provider coverage everywhere. |
| Hydrology | Background collector and status/observation views for two regional CWC/NWDP resources (Krishna-basin water level and Andhra Pradesh rainfall). These are not global gauge coverage. |
| Environmental catalog and coverage | Authenticated stored-record query and configured-scope panel. Counts are page-scoped; the panel does not verify global provider coverage. |
| Maps and GIS | Interactive location selection, a separate community incident map, saved legacy estimate markers, and Kochi-area reference layers. Community reports are unverified until reviewed; prediction markers are not observed hazard extents; GIS layers are not global. |
| Community incident reports | Authenticated global-coordinate reports with pending/review statuses, owner edits, reviewer history, redacted global map listings, and descriptive counts. They are user submissions—not official observations or warnings. No evidence files are uploaded. |
| Satellite | Authenticated Sentinel Catalog search and bounded Sentinel-2 TIFF request/download paths exist. Live application access depends on backend credentials and was not proven by automated tests; imagery is not hazard detection and is not guaranteed to be pinned to the displayed Catalog item. |
| Historical analytics | Descriptive summaries from supplied EM-DAT extracts. These are not live event monitoring, complete global surveillance, or model labels. |
| Digital Twin | React Stage 1 is a deterministic, illustrative Kochi rainfall-input scenario. It is not a physical flood model, forecast, inundation map, or emergency warning. The separate backend simulation API is a weather-based what-if workflow. |
| Resources, recommendations, alerts | Inventory and planning workflows are available. Demand priority is user-entered; route ordering is straight-line. Alerts are saved application estimates, not official warnings or external notifications. |
| Assistant | Requires a separately running local Ollama service and configured model. It has no web search and does not replace source-backed application results. |
| Flood prediction / ML | **Unavailable.** Readiness is `NOT_READY`; the flood prediction endpoint returns HTTP 503. Non-flood heuristic scores are unvalidated demonstrations. No validated global accuracy claim is available. |

---

## 🛠 Tech Stack

| **Category** | **Technologies** |
|--------------|------------------|
| Frontend | React.js, HTML, CSS, JavaScript |
| Backend | Python, FastAPI |
| Machine Learning | Scikit-learn |
| Explainable AI | SHAP |
| Database | SQLite (local default), PostgreSQL/PostGIS (configured deployments) |
| GIS | Leaflet.js, OpenStreetMap |
| Data Processing | Pandas, NumPy |
| Tools | Git, GitHub |

---

## 📂 Project Structure
```text
disaster-management-system/
│
├── ai-assistant/
├── alerts/
├── backend/
│   ├── app/                 FastAPI application
│   ├── data/legacy/         Preserved older local database copies
│   └── disasterguard.db     Local runtime SQLite database
├── database/                PostgreSQL/PostGIS schema and migrations
├── frontend/
├── ml/                      Datasets, preprocessing and models
├── gis/
├── digital-twin/
├── explainable-ai/
├── resource-optimization/
├── docs/
└── README.md
```
---

## 🏗 Architecture and workflow

The React/Vite client uses the FastAPI REST API for authentication and protected application workflows. SQLAlchemy stores application records in SQLite by default; PostgreSQL/PostGIS support files exist, but production deployment/migrations are not certified. Leaflet/OpenStreetMap provides maps; configured backend collectors store weather and regional hydrology observations. Historical EM-DAT analytics and local reference GIS are separate from live observations.

Typical workflow:

```text
Register / sign in
      → choose a WGS 84 location
      → inspect on-demand weather, configured source status and stored environmental records
      → review descriptive history and reference GIS
      → submit or review clearly labeled community incident reports
      → use resource-planning, recommendations or in-app estimate-alert workflows as demonstrations
      → optionally run the illustrative Digital Twin
```

The workflow does not produce a validated worldwide hazard forecast. Flood inference remains gated with HTTP 503. Existing saved estimates and heuristic categories must not be used for emergency decisions.

### System modules

- **Risk/readiness:** `/api/data-readiness` reports model/data state. Flood inference remains unavailable until validated training data, labels, a compatible artifact, and a matching runtime feature builder and evaluation evidence exist.
- **Explainability:** SHAP contributions are only meaningful for compatible model output; they do not establish model validity.
- **Maps:** displays saved account estimates and available Kochi reference layers, not predicted hazard extents or global GIS.
- **Incident reports:** authenticated community submissions are separate from observations, historical datasets, forecasts, satellite imagery, and prediction records. Only offline-provisioned reviewers may verify them. Country/region attribution and file upload are not implemented.
- **Digital Twin:** see the [Stage 1 guide](./docs/DIGITAL_TWIN_STAGE_1.md) for its illustrative inputs, limits, and non-physical method.
- **Recommendations/resources/alerts:** application workflows, not official emergency authority or automatic impact assessment. No SMS/email/push delivery is configured.

---

## 📊 Scope and limitations

The product intent is global: users may select valid WGS 84 coordinates worldwide. This does **not** establish global environmental data availability, complete coverage, or validated prediction capability. Kochi, Godavari, and Krishna are development/test regions only. Current CWC/NWDP feeds and packaged GIS are regional; weather is model-derived and depends on provider availability; satellite requests are query-specific. See the [global hazard coverage audit](./docs/PHASE_2_12_GLOBAL_HAZARD_DATA_COVERAGE_AUDIT.md) and [final submission readiness report](./docs/FINAL_SUBMISSION_READINESS.md).

Flood ML remains `NOT_READY` and the flood inference API returns HTTP 503. Historical reports are incomplete and descriptive, not event-free labels. The Digital Twin is illustrative, non-physical, and Kochi-only. Do not present any score, saved marker, data gap, or empty result as an official warning or proof that a hazard is absent.

## ⚙ Installation and startup (Windows PowerShell)

### Prerequisites

- Python 3.10 or newer and pip
- Node.js 18 or newer and npm
- Git
- Optional: Ollama and the configured model for the assistant
- Optional: backend-only Copernicus OAuth credentials for satellite routes

### 1. Configure and start the backend

From the repository root:

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `backend\.env` and replace `JWT_SECRET_KEY` with a long random secret. Keep this file private and uncommitted. The default database is local SQLite; `DATABASE_URL` can be left at its example value for local use. `FRONTEND_ORIGINS` defaults to `http://localhost:5173`. Do not add provider credentials to frontend configuration.

Start the backend from `backend\`:

```powershell
python -m uvicorn app.main:app --reload
```

The API is at <http://localhost:8000>; interactive API docs are at <http://localhost:8000/docs>. Startup launches the configured Open-Meteo and NWDP/CWC background collectors, which require provider/network access to collect data. One Uvicorn worker is recommended for the in-process schedulers.

### 2. Configure and start the frontend

In a second PowerShell terminal, from the repository root:

```powershell
cd frontend
Copy-Item .env.example .env
npm ci
npm run dev
```

Vite serves <http://localhost:5173>. `VITE_API_BASE` defaults to `http://localhost:8000`; change it in `frontend\.env` only when the backend runs elsewhere. The backend `FRONTEND_ORIGINS` must include the frontend origin.

### 3. Tests and production build

From the repository root:

```powershell
python -m pytest backend\tests ml -q
```

From `frontend\`:

```powershell
npm.cmd test
npm.cmd run build
```

Backend and frontend tests mock external providers; these checks do not prove live provider access. See [`backend/README.md`](./backend/README.md), [`frontend/README.md`](./frontend/README.md), and [`docs/`](./docs) for module and source details.

All project code and data should remain under this project directory. The active local SQLite database is `backend/disasterguard.db`; relative SQLite `DATABASE_URL` values resolve there even when the backend is started from another directory. Older local database files, if present, are preserved separately in `backend/data/legacy/` and are not used at runtime. Temporary caches, virtual environments, and generated test output are local tooling artifacts, not project data.

---

## 🎯 Project objectives

The academic project explores how environmental data, historical context, mapping, scenario tools, and planning workflows could support disaster decision-making. Validated multi-hazard and worldwide prediction is a future objective, not a current capability. Any eventual operational use requires hazard-specific sources, permissions, validated targets and models, uncertainty evaluation, and responsible deployment.

---

## 👨‍💻 Developed By

DisasterGuard AI Team

B.Tech – Information Technology

Academic Project – 2026-27

GitHub: https://github.com/eddulapreethi/disaster-management-system.git

---

## 📄 License

This project is developed for educational and academic purposes.

---
