# Flood ML readiness blockers

**Status:** Historical descriptive analytics are `READY`; supervised training, compatible model, runtime feature inference, and prediction remain `NOT_READY`.

## Intended target

The old model contract calls its regression target `FloodProbability`, but repository evidence does not establish that the values are calibrated event probabilities. The candidate environmental pipeline does not select or construct a flood target; its target status is `UNSELECTED`. There is no validated, per-location negative monitoring coverage from which non-events may be inferred.

Before training, the project owner/domain reviewer must approve:

- whether the target is an observed flood occurrence, a continuous severity/index, or a calibrated probability;
- the geographic unit, event definition, forecast horizon and time window;
- authoritative positive-label source and a method for complete negative-monitoring coverage;
- spatial/temporal alignment and grouping rules, including station/site/event leakage controls.

Absence of an event record is not a valid negative label.

## Data available and pipeline state

- The reproducible analytics pipeline validates the six supplied EM-DAT extracts (8,810 rows, 8,810 unique IDs, no cross-extract overlap) and produces descriptive counts/impact summaries. See `docs/HISTORICAL_DATASET_ASSESSMENT.md` and `docs/ML_PIPELINE_EXECUTION_REPORT.md`. Analytics readiness is not training readiness.
- The repository includes EM-DAT historical disaster records. Those event/impact records do not provide a location/time-matched sequence of environmental predictors plus verified flood/no-flood labels.
- The pre-existing untracked Open-Meteo archive downloader requests real daily historical environmental predictors at the Kochi study point and writes a hash/provenance manifest. It refuses to overwrite a raw file unless explicitly passed `--force`.
- The corresponding predictor builder constructs six source-measured weather features: 1-, 3-, and 7-day antecedent precipitation, mean temperature, mean humidity, and maximum wind speed. It records units, requested/returned coordinates, UTC windows, source and file hashes, and missing-value/target limitations.
- The six candidate features are not the old 20-feature ordinal schema, are explicitly unavailable at live inference, and cannot be passed to the existing model.
- The current versioned candidate contract is documented in `docs/FEATURE_CONTRACT.md` and `ml/preprocessing/feature_contract.json`; the machine-readable contract is checked against the Python feature schema.
- The candidate builder can align explicit labels only by exact location and UTC target window, requires documented approval fields, requires evidence fields, and does not infer negatives. A manifest does not authenticate the source or prove a scientific label definition.
- No Open-Meteo archive was downloaded or incorporated during this review. The source's selected underlying model, exact native spatial resolution and redistribution terms need review before retaining/redistributing a real extract. No target labels or model artifact were generated.
- The environmental predictor processor previously replaced a large 7-day precipitation sum with an unrelated fixed arithmetic sum. That fabricated substitution is removed and regression-tested; the output now retains the actual sum of the seven source measurements.

## Required old-model feature contract

The existing model's 20 fields remain indices with an old numeric range of 0–16. Authoritative meanings, units, sources and transformations are not documented. No correspondence between those indices and live Open-Meteo/NWDP values is established. The project must not invent conversions or expose manual feature sliders.

## Runtime and model evidence still required

1. Authorize/license and document a sufficiently representative multi-site dataset with verified environmental measurements and flood labels, including complete monitoring coverage for negative examples.
2. Approve target semantics, geographic/time resolution, units, issue time, prediction horizon, label confidence/coverage policy, and source provenance.
3. Choose either a fully verified mapping for the old feature contract or a deliberate, versioned replacement model schema. Do not silently mix them.
4. Implement a deterministic runtime feature builder that uses only data available at the prediction issue time and validates freshness, station/location matching, units and missing inputs.
5. Validate with chronological and site/event-grouped holdouts that prevent temporal and spatial leakage; compare against a meaningful baseline and report uncertainty, calibration if predicting probabilities, class imbalance, sample coverage and independent-site performance.
6. Record schema/model versions, exact data/manifest hashes, preprocessing and training configuration, split policy, measured metrics and source/license evidence with the artifact.
7. Test artifact loading, inference, unavailable/stale input handling and readiness behavior against the same schema before allowing the API to persist a result.

Until each required gate is met and reviewed, keep `/api/predictions` flood requests at HTTP 503 and do not use legacy scores for alerts or emergency decisions. The current readiness checks and tests enforcing this state must remain enabled.
