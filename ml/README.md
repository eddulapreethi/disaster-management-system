# DisasterGuard flood ML pipeline

## Current verified state

There is currently **no trained model artifact** under `ml/models/trained_models/`. The readiness service loads and checks an artifact instead of treating file existence as proof of readiness. Until a compatible artifact and backend runtime feature builder are implemented, the flood prediction API returns HTTP 503 and does not save heuristic scores as flood predictions. Historical prediction rows may contain legacy demonstrator scores and are not verified forecasts.

The workbook present in this checkout is `ml/datasets/historical_disasters/EM-DAT/public_emdat_custom_request_2026-09-30_65676a52-2bac-4e9b-b454-70d54b055fa3.xlsx` (not the `historical_data/EM-DAT/public_emdat_custom_request_2026.xlsx` path mentioned in earlier task notes). It contains an EM-DAT event sheet with 10,902 rows, 47 source columns, and start years 2000–2026. The processed flood-event table has 4,299 rows. Those tables contain event categories, event-level impacts, country/location descriptions and incompletely populated coordinates; they do not contain the 20 model predictors or validated continuous flood labels. EM-DAT is not used as a source of per-location rainfall, river observations, or probabilities.

The runtime weather collector stores Open-Meteo observations in the application database; it is not a historical weather archive joined to EM-DAT. No compatible training dataset or hydrology training table is present. Therefore the repository does not have evidence to train a scientifically valid model, and all three ML readiness statuses correctly remain `NOT_READY`. Unit-test-only synthetic fixtures are not operational model data and are never installed as an artifact.

### Current data-pipeline diagnosis

The backend inspection and live checks confirmed that weather freshness is based on provider `observation_time`, while `fetched_at` is tracked separately. SQLite strips timezone metadata from `DateTime(timezone=True)` columns; its naive values are stored in UTC, but JSON previously omitted the UTC offset. Browser parsing therefore treated them as local time and could make a recent reading appear hours older. Observation API serialization now emits UTC `Z` timestamps, and readiness rejects observations more than five minutes in the future.

The latest database check showed an Open-Meteo observation for Kochi at `2026-10-10T17:45:00Z`, within the configured 7,200-second freshness limit. CWC collection successfully checked both configured resources on `2026-10-10T17:55:58Z` but received and inserted zero new records with no parse errors. The latest stored Krishna water-level observation was `2026-09-27T21:30:00Z` at Mantralayam (307.981 m); the latest Andhra rainfall observation was `2026-09-27T01:30:00Z` at Koida (0.5 mm). A live read of the official resource pages agreed that the latest telemetry in the returned newest-ID pages was old. Therefore hydrology is stale source telemetry, not evidence of a current collector failure; frequent polling cannot make the source measurements newer.

The immediate saved-prediction weather-panel failure was the missing UTC suffix on naive SQLite timestamps, not a newly fetched value being mistaken for the observation time. The backend and browser now compare observation time and report stale/future/invalid cases distinctly. A real flood prediction still cannot be produced: the old 20 features remain undocumented indices, no compatible labeled training data or model artifact exists, and no runtime mapping from weather/hydrology to those features is justified. The flood API now responds with service-unavailable and saves no score in that state.

## Existing feature contract and its limits

The legacy candidate is a regression schema with `FloodProbability` values from 0 to 1. The term does **not** prove these values are calibrated event probabilities. The 20 feature names below are the existing contract; the repository has no authoritative dictionary giving their measurement definition, units, source or transformations. Their old 0–16 range is a numeric constraint, not a validated physical unit. No weather variable is converted into these indices.

| Name | Meaning currently documented | Type | Unit / range | Missing values | Source / transformation |
|---|---|---|---|---|---|
| `MonsoonIntensity` | MonsoonIntensity factor | numeric | Unverified index, 0–16 | Rejected | No verified source or transformation |
| `TopographyDrainage` | TopographyDrainage factor | numeric | Unverified index, 0–16 | Rejected | No verified source or transformation |
| `RiverManagement` | RiverManagement factor | numeric | Unverified index, 0–16 | Rejected | No verified source or transformation |
| `Deforestation` | Deforestation factor | numeric | Unverified index, 0–16 | Rejected | No verified source or transformation |
| `Urbanization` | Urbanization factor | numeric | Unverified index, 0–16 | Rejected | No verified source or transformation |
| `ClimateChange` | ClimateChange factor | numeric | Unverified index, 0–16 | Rejected | No verified source or transformation |
| `DamsQuality` | DamsQuality factor | numeric | Unverified index, 0–16 | Rejected | No verified source or transformation |
| `Siltation` | Siltation factor | numeric | Unverified index, 0–16 | Rejected | No verified source or transformation |
| `AgriculturalPractices` | AgriculturalPractices factor | numeric | Unverified index, 0–16 | Rejected | No verified source or transformation |
| `Encroachments` | Encroachments factor | numeric | Unverified index, 0–16 | Rejected | No verified source or transformation |
| `IneffectiveDisasterPreparedness` | IneffectiveDisasterPreparedness factor | numeric | Unverified index, 0–16 | Rejected | No verified source or transformation |
| `DrainageSystems` | DrainageSystems factor | numeric | Unverified index, 0–16 | Rejected | No verified source or transformation |
| `CoastalVulnerability` | CoastalVulnerability factor | numeric | Unverified index, 0–16 | Rejected | No verified source or transformation |
| `Landslides` | Landslides factor | numeric | Unverified index, 0–16 | Rejected | No verified source or transformation |
| `Watersheds` | Watersheds factor | numeric | Unverified index, 0–16 | Rejected | No verified source or transformation |
| `DeterioratingInfrastructure` | DeterioratingInfrastructure factor | numeric | Unverified index, 0–16 | Rejected | No verified source or transformation |
| `PopulationScore` | PopulationScore factor | numeric | Unverified index, 0–16 | Rejected | No verified source or transformation |
| `WetlandLoss` | WetlandLoss factor | numeric | Unverified index, 0–16 | Rejected | No verified source or transformation |
| `InadequatePlanning` | InadequatePlanning factor | numeric | Unverified index, 0–16 | Rejected | No verified source or transformation |
| `PoliticalFactors` | PoliticalFactors factor | numeric | Unverified index, 0–16 | Rejected | No verified source or transformation |

The machine-readable order/range is `FLOOD_FEATURES` and `FLOOD_FEATURE_SCHEMA` in `ml/preprocessing/feature_engineering.py`. The schema records the missing provenance rather than asserting guessed definitions. Training and inference validate numeric finite values and fixed order; training rejects missing feature values, and inference rejects missing/extra feature keys. The training pipeline's median imputer is fitted only on the training fold but is not permission to pass missing rows.

## Data required before training

Provide an authorized CSV where each row has all 20 documented features, a `FloodProbability` continuous target with defensible target semantics, and one of `observation_time`, `event_date`, `start_date`, `timestamp`, `date`, or `start_year` for chronological evaluation. The CSV must be joined using a documented spatial and temporal rule; an EM-DAT event's country/date alone is not a location-specific environmental label. Include a sidecar `<csv-stem>.manifest.json` declaring:

- dataset name/version, source/reference, license and geographic/temporal coverage;
- row definition, grouping/leakage policy, and the spatial-temporal linkage used;
- a precise target definition and `target_interpretation: "continuous_index"`; and
- `feature_schema_version: "flood-risk-factors-v1"` plus a definition for every canonical feature, including its meaning, unit, source, and transformation.

This regression pipeline does not claim calibrated probabilities. A probability target requires a separately validated probability-calibration pipeline. A manifest documents analyst assertions; it does not independently authenticate a data source or prove scientific validity.

Example manifest structure (fill in real evidence; placeholder values are rejected by the trainer):

```json
{
  "dataset_name": "verified flood study",
  "dataset_version": "2026-01",
  "source_name": "provider or study",
  "source_reference": "DOI or official dataset URL",
  "license": "license name",
  "geographic_coverage": "study area and spatial resolution",
  "temporal_coverage": "start/end timestamps and timezone",
  "spatiotemporal_linkage": "documented location/time matching rule",
  "row_definition": "one row per documented location and observation window",
  "grouping_policy": "event/site grouping and split leakage controls",
  "target_definition": "what the continuous 0-1 index measures and how it was labeled",
  "target_interpretation": "continuous_index",
  "feature_schema_version": "flood-risk-factors-v1",
  "feature_definitions": {
    "MonsoonIntensity": {
      "meaning": "TODO: precise documented definition",
      "data_type": "numeric",
      "unit": "TODO: dimensionless ordinal index unit",
      "minimum": 0,
      "maximum": 16,
      "source": "TODO: source field and source reference",
      "transformation": "TODO: reproducible conversion"
    }
  }
}
```

`feature_definitions` must include all 20 names from the schema. Do not copy this single-feature fragment as a complete manifest.

## Train and evaluate

Install `ml/requirements.txt` in the Python environment used by the backend. From the repository root:

```powershell
python -m ml.preprocessing.flood_feature_integration --input path\to\verified_flood_training_data.csv --output ml\datasets\historical_data\processed\flood_feature_matrix.csv
python -m ml.training.train_model path\to\verified_flood_training_data.csv
```

The sidecar manifest is required by default; pass `--manifest path\to\manifest.json` to override it. The trainer validates the manifest and feature/target ranges, removes exact duplicate rows, requires at least five labeled records, and holds out the latest distinct time periods. It evaluates a `RandomForestRegressor` against a mean `DummyRegressor` baseline and records MAE, RMSE and (when defined) R². Small datasets may make these metrics unstable; five rows is a software minimum, not a scientifically sufficient sample size. The artifact records the dataset and manifest hashes, schema/version, training date, target definition, split and measured metrics at `ml/models/trained_models/flood_risk_model.joblib`. No artifact is committed or trained from fabricated rows.

The current split is chronological. If related observations are grouped by location/event, the supplied manifest must describe that structure; automatic group-aware chronological splitting is not yet implemented, so such data must first be aggregated or split without groups crossing the temporal boundary. Artifact metadata records package versions, but model loading currently requires a compatible pipeline/schema rather than enforcing an exact package-version match. `--tune` performs parameter search only within the training period; it does not remedy insufficient or biased data.

## Inference, readiness and UI behavior

`ml.prediction.predict.load_model_artifact` loads once per unchanged file and verifies its pipeline, exact ordered features, schema version, manifest hash, target metadata, holdout/baseline metrics, and a finite in-range probe inference. Invalid or incompatible artifacts are `NOT_READY`; they are not silently replaced with the weather heuristic. Inference requires the exact 20-key input object and validates each value. The output is explicitly a continuous target estimate, not a calibrated probability. SHAP is attempted against the actual fitted model; if the explainer is incompatible/unavailable, the prediction remains labeled without fabricated contributions and the limitation is logged.

`GET /api/data-readiness` reports:

- `ml_model=READY` only when an installed artifact passes loading, metadata, schema, metrics, and probe checks;
- `features=READY` only when the canonical schema and a complete declared training manifest are available; and
- `prediction=READY` only when a verified runtime feature builder can supply the model schema.

The last requirement is not implemented: stored Open-Meteo weather and NWDP hydrology fields do not map to the undocumented ordinal indices. Consequently prediction remains `NOT_READY` even after model training until those feature definitions and the runtime builder are validated. The frontend does not expose arbitrary 0–16 feature sliders. A request for a flood prediction returns HTTP 503 until a valid model and feature builder are available. Missing or stale weather remains a data-quality error and is not replaced by a local fallback.
