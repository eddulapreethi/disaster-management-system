# ML readiness status

The project does not currently have a verified flood-risk model artifact or a complete runtime feature builder that matches the historical event records. The dashboard therefore marks ML readiness separately from historical analytics readiness.

The relevant blockers remain:

- no validated trained model artifact at `ml/models/trained_models/flood_risk_model.joblib`
- no validated site-level flood target using complete, aligned non-event coverage
- no proven environmental feature contract mapped to event records and timestamps
- no live feature builder for runtime inference that has been validated against the accepted schema

Historical analytics can remain ready while ML inference remains blocked, which is the required separation for this project.
