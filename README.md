# 🌍 DisasterGuard AI

## AI-Powered Disaster Prediction & Decision Support System

DisasterGuard AI is an academic disaster-management demonstration that integrates weather, hydrological, historical, satellite and GIS data with a web application for data readiness, illustrative risk estimates, mapping, scenario simulation, recommendations, resource planning and in-app alerts.

> **Readiness notice:** Flood prediction is currently disabled (the API returns HTTP 503) because there is no compatible trained artifact, verified feature-source mapping or runtime feature builder. Existing scores are unverified history; heuristic estimates and Digital Twin scenarios are not validated forecasts or official warnings. See [`docs/PROJECT_COMPLETION_STATUS.md`](./docs/PROJECT_COMPLETION_STATUS.md).

---

## ✨ Features

- 🤖 Flood model readiness gate and demonstrator weather estimates for supported non-flood hazards
- 🔍 SHAP explanations only when a compatible trained model is available
- 🗺 GIS-Based Risk Visualization
- 🧪 Digital Twin Disaster Simulation
- 🧠 AI-Based Emergency Recommendations
- 🚑 Emergency Resource Optimization
- 🚨 In-app estimate alerts (no SMS/email/push delivery)
- 🌦 Weather Data Integration
- 💧 Hydrological Data Integration
- 🛰 Satellite Data Integration
- 📚 Historical Disaster Data Analysis
- 📊 Disaster Risk Analysis
- 👤 Bearer-token user authentication (no role-based access control)

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

## 🏗 System Modules

🤖 Disaster Risk Prediction

Flood inference remains unavailable until validated training data, model artifact and matching runtime features are supplied. Existing wildfire/storm estimates are demonstrator heuristics, not validated forecasts.

🔍 Explainable AI

Uses SHAP when a compatible trained artifact is installed; no fabricated explanations are returned when it is unavailable.

🗺 GIS Risk Visualization

Displays predicted disaster-risk areas and locations using an interactive GIS map.

🧪 Digital Twin Simulation

The Stage 1 Digital Twin provides a local, deterministic rainfall what-if timeline over the Kochi reference GIS map. Its animated symbol is not a flood extent, forecast, or warning. See the [Stage 1 Digital Twin guide](./docs/DIGITAL_TWIN_STAGE_1.md) for usage, assumptions, validation, and Stage 2 requirements.

🧠 AI Emergency Recommendations

Generates emergency guidance and recommendations based on predicted risks, explanations, and simulation results.

🚑 Resource Optimization

Supports emergency resource allocation based on predicted risk areas and available resources.

🚨 Emergency Alerts

Persists in-app alerts for eligible demonstrator estimates above a configurable threshold. These are not official warnings and have no external message delivery.

---

## 📊 Data Sources

The system works with multiple categories of disaster-related data:

🌦 Weather Data  
💧 Hydrological Data  
📚 Historical Disaster Data  
🛰 Satellite Data  
🗺 GIS Data  

These data sources are processed and integrated before being used for disaster-risk prediction.

---

## 🚀 Project Workflow

```text

Data Collection
      │
      ▼
Data Preprocessing
      │
      ▼
Feature Engineering
      │
      ▼
AI/ML Disaster Prediction
      │
      ▼
Risk Assessment
      │
      ├──► SHAP Explanation
      │
      ├──► GIS Risk Map
      │
      └──► Digital Twin Simulation
                    │
                    ▼
            AI Recommendations
                    │
                    ▼
            Resource Optimization
                    │
                    ▼
             Emergency Alerts
```
---

## ⚙ Installation

Clone the Repository  
- git clone https://github.com/eddulapreethi/disaster-management-system.git  
Navigate to the Project  
- cd disaster-management-system
Backend Setup  
- cd backend
- py -m venv .venv
- .\.venv\Scripts\Activate.ps1
- pip install -r requirements.txt
- Copy-Item .env.example .env
- Set a long random JWT_SECRET_KEY in backend\.env

Start the backend from the `backend` directory:

- uvicorn app.main:app --reload

In a second terminal, start the frontend:

- cd frontend
- npm ci
- npm run dev

Run automated checks:

- From the repository root: `python -m pytest backend\tests ml -q`
- From `frontend`: `npm test` and `npm run build`

The backend defaults to a local SQLite database. External Ollama and Copernicus services require their own local installation or server-side credentials. Review [`backend/README.md`](./backend/README.md) and [`docs/`](./docs) before enabling integrations or using the project operationally.

All project code and data should remain under this project directory. The active local SQLite database is `backend/disasterguard.db`; relative SQLite `DATABASE_URL` values resolve there even when the backend is started from another directory. Older local database files, if present, are preserved separately in `backend/data/legacy/` and are not used at runtime. Temporary caches, virtual environments, and generated test output are local tooling artifacts, not project data.

---

## 🎯 Project Objectives

- Predict potential disaster risks using AI/ML.
- Integrate multiple disaster-related data sources.
- Explain AI predictions using SHAP.
- Visualize disaster risks using GIS.
- Simulate disaster scenarios using Digital Twin technology.
- Generate AI-based emergency recommendations.
- Optimize emergency resource allocation.
- Provide timely disaster alerts.
- Support data-driven emergency decision-making.

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
