# DisasterGuard AI Machine Learning

This is a flood-first ML prototype. It trains a scikit-learn regression model using the 20 model features declared in `preprocessing/feature_engineering.py` and a numeric `FloodProbability` target in the range 0–1. The frontend currently submits those same named feature values on a 0–16 scale. It does not ship a fabricated or pre-trained model.

The current trainer reads one prepared CSV; it does not fetch Open-Meteo, CWC/NWIC, EM-DAT, satellite imagery or GIS sources. Raw provider fields must be licensed, cleaned, aligned by time/location and transformed into the model's declared feature schema before training. Raw weather/hydrological columns are not automatically equivalent to the existing 20 model features. No live data collector is implemented.

The frontend fetches current Open-Meteo rainfall, temperature and wind when a user runs a prediction. Those values are stored with the prediction and are used by the labeled heuristic fallback, but the trained flood model currently predicts from the 20 feature-slider values only. Do not interpret its result as weather-driven until a real labeled dataset and feature-engineering mapping are available and the model is retrained with matching inputs.

## Setup

From the project root, install the ML dependencies into the Python environment selected in VS Code:

```powershell
python -m pip install -r ml/requirements.txt
```

## Train

Place an authorized historical flood CSV under `ml/datasets/historical_disasters/`. It must contain every feature in `FLOOD_FEATURES` plus a numeric `FloodProbability` column with values from 0 to 1. The current feature schema is the model's 20 risk-factor inputs, not raw Open-Meteo weather columns. Then run from the project root:

```powershell
python -m ml.training.train_model ml/datasets/historical_disasters/flood_data.csv
```

The script evaluates on a holdout split and saves `ml/models/trained_models/flood_risk_model.joblib`. Add `--tune` to run cross-validated hyperparameter search. The reported MAE and RMSE are in probability units (0–1). The backend uses this default artifact path; set `DISASTERGUARD_MODEL_PATH` in `backend/.env` to point it elsewhere.

## Predict

Create a JSON file containing all 20 feature keys (each from 0 to 16), then run:

```powershell
python -m ml.prediction.predict input.json
```

Inference returns a probability, a dashboard-compatible 0–100 score and low/medium/high band, plus TreeSHAP feature contributions. The authenticated backend prediction endpoint calls this pipeline for flood requests when the artifact is available. Without it, the backend clearly labels and stores its weather-based demonstrator heuristic instead; no SHAP contributions are returned for that fallback.

## Data folders

`datasets/weather`, `hydrological`, `historical_disasters`, `satellite`, and `gis` are for authorized model-development inputs only. Runtime API observations belong in the application database; map-display layers belong under `gis/data/`. Dataset folders contain guidance, not fabricated source data. Record provider, license, units, CRS, timestamps and preprocessing for each real dataset.
