# 🌍 DisasterGuard AI

## AI-Powered Disaster Prediction & Decision Support System

DisasterGuard AI is an AI-powered disaster management and early warning platform designed to predict potential disaster risks and support emergency decision-making. By integrating weather, hydrological, historical disaster, satellite, and GIS data with AI/ML, the platform provides risk prediction, explainable AI analysis, GIS-based visualization, Digital Twin simulation, emergency recommendations, resource optimization, and disaster alerts.

---

## ✨ Features

- 🤖 AI-Based Disaster Risk Prediction
- 🔍 Explainable AI using SHAP
- 🗺 GIS-Based Risk Visualization
- 🧪 Digital Twin Disaster Simulation
- 🧠 AI-Based Emergency Recommendations
- 🚑 Emergency Resource Optimization
- 🚨 Emergency Alerts & Notifications
- 🌦 Weather Data Integration
- 💧 Hydrological Data Integration
- 🛰 Satellite Data Integration
- 📚 Historical Disaster Data Analysis
- 📊 Disaster Risk Analysis
- 👥 Role-Based Access

---

## 🛠 Tech Stack

| **Category** | **Technologies** |
|--------------|------------------|
| Frontend | React.js, HTML, CSS, JavaScript |
| Backend | Python, FastAPI |
| Machine Learning | Scikit-learn |
| Explainable AI | SHAP |
| Database | PostgreSQL |
| GIS | Leaflet.js, OpenStreetMap |
| Data Processing | Pandas, NumPy |
| Tools | Git, GitHub |

---

## 📂 Project Structure

```text
DisasterGuard-AI
│
├── backend/
│   └── FastAPI Application
│
├── frontend/
│   └── React Application
│
├── ml/
│   ├── datasets/
│   ├── preprocessing/
│   ├── models/
│   └── prediction/
│
├── gis/
│
├── digital-twin/
│
├── docs/
│   └── diagrams/
│
├── screenshots/
│
├── .env.example
├── .gitignore
└── README.md

---

##🏗 System Modules

🤖 Disaster Risk Prediction

Uses environmental and historical disaster data to predict potential disaster risks and classify them into different risk levels.

🔍 Explainable AI

Uses SHAP-based analysis to identify the important factors contributing to a disaster-risk prediction and provide understandable explanations.

🗺 GIS Risk Visualization

Displays predicted disaster-risk areas and locations using an interactive GIS map.

🧪 Digital Twin Simulation

Provides what-if scenario analysis by simulating changes in environmental conditions and observing their possible impact on disaster risk.

🧠 AI Emergency Recommendations

Generates emergency guidance and recommendations based on predicted risks, explanations, and simulation results.

🚑 Resource Optimization

Supports emergency resource allocation based on predicted risk areas and available resources.

🚨 Emergency Alerts

Generates alerts for relevant users when the predicted risk reaches a configured level.

---

##📊 Data Sources

The system works with multiple categories of disaster-related data:

🌦 Weather Data
💧 Hydrological Data
📚 Historical Disaster Data
🛰 Satellite Data
🗺 GIS Data

These data sources are processed and integrated before being used for disaster-risk prediction.

---

##🚀 Project Workflow

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

---

##⚙ Installation

Clone the Repository
git clone https://github.com/YOUR_USERNAME/DisasterGuard-AI.git
Navigate to the Project
cd DisasterGuard-AI
Backend Setup
cd backend
python -m venv venv

Activate the virtual environment and install dependencies:

pip install -r requirements.txt
Frontend Setup
cd frontend
npm install
Configure
Configure the database
Add required API keys
Configure environment variables
Ensure all required dependencies are installed
Run the Project

Start the backend:

uvicorn app.main:app --reload

Start the frontend:

npm run dev

---

##🎯 Project Objectives

Predict potential disaster risks using AI/ML.
Integrate multiple disaster-related data sources.
Explain AI predictions using SHAP.
Visualize disaster risks using GIS.
Simulate disaster scenarios using Digital Twin technology.
Generate AI-based emergency recommendations.
Optimize emergency resource allocation.
Provide timely disaster alerts.
Support data-driven emergency decision-making.

---

##👨‍💻 Developed By

DisasterGuard AI Team

B.Tech – Information Technology

Academic Project – 2026-27

GitHub: https://github.com/eddulapreethi/disaster-management-system.git

---

##📄 License

This project is developed for educational and academic purposes.

---
