# Hydrological Training Data

Store authorized historical river, rainfall, reservoir and discharge observations used for model development here. Record provider, station/location identifiers, units, observation interval, timezone, quality flags and licensing.

Live telemetry should be collected by a backend service and stored in the application database, not copied into this folder on every refresh. The current flood model expects its documented feature columns, so hydrological observations require an explicit feature-engineering step before training. No sample data is included.

## Stage 2 Part B audit

The downloaded Godavari and Krishna CWC/NWDP CSVs under `raw/` were audited without modifying them. Results, observed date ranges, duplicate and missing-value counts, timestamp gaps, metadata findings, and unresolved limitations are recorded in [`STAGE_2_PART_B_HYDROLOGICAL_AUDIT.md`](../../../docs/STAGE_2_PART_B_HYDROLOGICAL_AUDIT.md) and its [machine-readable JSON report](../../../docs/STAGE_2_PART_B_HYDROLOGICAL_AUDIT.json).

The audit is data preparation only. It does not validate a flood prediction model or establish hydraulic-modelling readiness. No normalized derivative was created because a verified station mapping and source timezone were not supplied; existing files under `processed/` were not overwritten.

The follow-up metadata/provenance review is documented in [`STAGE_2_PART_B2_METADATA_PROVENANCE_REVIEW.md`](../../../docs/STAGE_2_PART_B2_METADATA_PROVENANCE_REVIEW.md). It records provider questions, raw-row examples for conflicting measurements, and why normalization remains blocked.

The human-review-only [CWC/NWIC clarification request draft](../../../docs/CWC_NWIC_PROVIDER_CLARIFICATION_REQUEST_DRAFT.md) and [structured metadata readiness gate](../../../docs/HYDROLOGICAL_METADATA_READINESS_GATE.json) track evidence needed before normalization. The request has not been sent; each dataset's required metadata fields remain `UNRESOLVED` until authoritative evidence is reviewed.

The [provider response tracker](../../../docs/CWC_NWIC_PROVIDER_RESPONSE_TRACKER.md) records response/evidence status and review instructions. The proposed contact remains unverified, no provider response is recorded, and both datasets remain blocked.

The [Stage 2 Part B.6 evidence-acquisition plan](../../../docs/HYDROLOGICAL_EVIDENCE_ACQUISITION_PLAN.json) maps every readiness field to planned evidence, authoritative sources, tracker questions, review steps, acceptance criteria, blockers, and dependencies. It is a plan only: no provider contact or evidence review has occurred, and all required fields remain unresolved.

The [Stage 2 ML Part 1 forecasting-feasibility report](../../../docs/STAGE_2_ML_PART_1_HYDROLOGICAL_FORECASTING_FEASIBILITY.md) profiles the raw CSVs without modifying them. Its status is `NOT_READY`; the one-hour water-level target and rainfall/discharge joins are not justified by the current metadata or observed cadence. No model was trained.
