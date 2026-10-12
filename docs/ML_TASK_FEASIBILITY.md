# Historical analytics and flood-ML feasibility

## Conclusion

The available EM-DAT data supports reproducible historical descriptive analytics (Task A): source-checked dataset inventory, event counts by year/type/country, reported-impact summaries, and data-quality/provenance reporting.

Supervised flood classification, severity regression, and calibrated probability forecasting (the predictive Tasks B/C) are **not currently supportable**. No model was trained, no labels were fabricated, and prediction readiness remains blocked.

## Evidence

- The six available hazard extracts contain 8,810 rows and 8,810 unique event IDs. The largest is the EM-DAT flood extract with 4,291 events.
- EM-DAT event records are not a complete monitoring panel. An absent event row cannot establish that a particular place was observed and flood-free.
- Only 1,006 (23.44%) flood rows have both valid coordinates. Several other hazard extracts have very low or no coordinate coverage.
- The extracts do not provide verified site-level rainfall, river levels, or a predictor/target series aligned to a defined forecast issue time and horizon.
- The existing 20 ordinal model inputs have no authoritative source, units, transformations, or interpretable mapping from current weather/hydrology data.
- A six-variable environmental predictor candidate exists, but it is historical daily archive data, has no approved flood target, and is marked unavailable for live inference. No compatible runtime builder or trained model artifact is present.
- There are no verified positive labels paired with complete negative-monitoring coverage and no approved spatial/time unit, event definition, or prediction horizon.

## Required evidence before predictive training

1. Domain approval of target semantics (observed event, severity, or probability), spatial unit, issue time, forecast horizon, and label window.
2. Authorized representative observations that directly support positive labels and documented complete-coverage evidence for negative labels.
3. Versioned alignment rules for labels and predictors, with location identity and UTC windows, and checks that exclude future information.
4. An approved feature schema and compatible runtime feature builder for exactly the same schema used in training.
5. Sufficient independent sites/events and time coverage for grouped, chronological holdouts; report coverage, class imbalance, baseline, uncertainty, and probability calibration if applicable.
6. Source licensing, exact dataset and transformation hashes, reproducible training configuration, artifact compatibility checks, and reviewed validation results.

Until those gates are met, prediction endpoints must remain unavailable (`NOT_READY`/HTTP 503 as applicable). Historical descriptive analytics being ready is not evidence of model readiness. A zero Digital Twin score is likewise not evidence that real-world flood risk is low.
