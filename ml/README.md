# DisasterGuard AI Machine Learning

This is a flood-first ML prototype. Its candidate schema contains the 20 features declared in `preprocessing/feature_engineering.py` and a numeric `FloodProbability` target in the range 0–1. The frontend currently submits those same named feature values on a 0–16 scale. No trained model is included.

The trainer reads one prepared CSV; it does not fetch Open-Meteo, CWC/NWIC, EM-DAT, satellite imagery or GIS sources. The processed EM-DAT tables contain event history and impacts, not the required environmental predictors or calibrated flood-probability labels. EM-DAT must not be converted into invented feature values or a proxy target. The previously generated `flood_feature_matrix.csv` used impact-derived proxies and has been removed; the integration command now fails closed until an independently labeled, time/location-aligned dataset already contains the required real features.

The backend collects current Open-Meteo weather and NWDP/CWC hydrology observations. Those live records are not automatically aligned to historic flood events or converted into the 20 model features. The weather values displayed when a user runs a prediction are context for the explicitly labeled heuristic fallback; they are not the trained model inputs.

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

The script requires at least five labeled rows and an observation/event time column. It holds out the latest time periods for evaluation, then saves a versioned artifact with the feature order, training-data SHA-256, timestamp, and measured test metrics at `ml/models/trained_models/flood_risk_model.joblib`. Add `--tune` to run cross-validated hyperparameter search on the training period. The reported MAE and RMSE are in probability units (0–1). No results should be reported until the input dataset has been independently verified. The backend uses this default artifact path; set `DISASTERGUARD_MODEL_PATH` in `backend/.env` to point it elsewhere.

## Predict

Create a JSON file containing all 20 feature keys (each from 0 to 16), then run:

```powershell
python -m ml.prediction.predict input.json
```

Inference returns a probability, a dashboard-compatible 0–100 score and low/medium/high band, plus TreeSHAP feature contributions, when a real compatible artifact is supplied. The authenticated backend prediction endpoint uses that pipeline for flood requests when the artifact is available. Without it, the backend labels and stores its weather-based demonstrator heuristic instead; no SHAP contributions are returned for that fallback.

## Data folders

`datasets/weather`, `hydrological`, `historical_disasters`, `satellite`, and `gis` are for authorized model-development inputs only. Runtime API observations belong in the application database; map-display layers belong under `gis/data/`. Dataset folders contain guidance, not fabricated source data. Record provider, license, units, CRS, timestamps and preprocessing for each real dataset.
