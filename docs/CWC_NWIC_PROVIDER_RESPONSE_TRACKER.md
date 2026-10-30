# CWC/NWIC Provider Response Tracker — Stage 2 Part B.4

## Tracking status

- **Request:** [CWC/NWIC clarification request draft](./CWC_NWIC_PROVIDER_CLARIFICATION_REQUEST_DRAFT.md)
- **Draft sent:** `NOT_RECORDED` — no sent copy or dispatch evidence is recorded in this repository.
- **External response:** `NOT_RECORDED` — no provider reply or evidence is attached in this repository. This does not establish whether a response exists outside the repository.
- **Proposed contact:** `rdcdte-cwc@nic.in`
- **Contact verification:** `UNVERIFIED` — the address is cited in existing project documentation from catalog metadata. The current address, role, and routing for these historical datasets have not been independently confirmed.
- **Dataset readiness:** Godavari `BLOCKED`; Krishna `BLOCKED`.
- **Readiness gate:** [`HYDROLOGICAL_METADATA_READINESS_GATE.json`](./HYDROLOGICAL_METADATA_READINESS_GATE.json) remains authoritative. Its 15 fields per dataset remain `UNRESOLVED`; no evidence status was changed by creating this tracker.
- **Normalization:** `BLOCKED`; no normalization or external contact was performed for this tracking task.

Response statuses used in this document:

- `NOT_RECORDED`: no response/evidence is recorded in the project repository; not a claim that no off-repository communication exists.
- `RECEIVED_PENDING_REVIEW`: provider material is attached or referenced but has not been assessed against the gate.
- `REVIEWED_INSUFFICIENT`: reviewed evidence does not satisfy the question or is not authoritative/applicable.
- `REVIEWED_ACTION_REQUIRED`: evidence was reviewed and additional clarification or technical action is needed.
- `REVIEWED_SUFFICIENT`: a reviewer determined the evidence answers the question for the stated scope. This alone does not change the readiness JSON; the reviewer must update the affected dataset field(s) with traceable evidence and justification.

Review decision values: `PENDING`, `SUFFICIENT_FOR_QUESTION`, `INSUFFICIENT`, or `CONFLICTING`. Do not use `SUFFICIENT_FOR_QUESTION` merely because an answer was received.

## Question-by-question tracking

No provider responses or evidence were available to record while preparing this tracker. The following entries are deliberately blank of provider claims.

| Draft question | Clarification topic | Scope | Response status | Evidence received | Evidence source | Review decision | Remaining action |
|---:|---|---|---|---|---|---|---|
|  1  |  Exact NWIC/NWDP package, dataset, resource, and version IDs  |  Both datasets  |  NOT_RECORDED  | None recorded | None recorded |  PENDING  |  Obtain authoritative identifiers and versioned resource documentation.  |
|  2  |  Official CWC/NWIC origin, generation/retrieval, query/filter, checksum, endpoint  |  Both datasets  |  NOT_RECORDED  | None recorded | None recorded |  PENDING  |  Obtain provenance details and link the official source to each exact local file.  |
|  3  |  Complete versus partial/filtered/paginated export and expected scope  |  Both datasets  |  NOT_RECORDED  | None recorded | None recorded |  PENDING  |  Obtain a completeness statement and exact expected station/time coverage.  |
|  4  |  Meaning of the filename's 2021–2025 label and verified coverage  |  Both datasets  |  NOT_RECORDED  | None recorded | None recorded |  PENDING  |  Obtain source coverage evidence; do not treat filenames as proof.  |
|  5  |  Stable physical gauge ID and authoritative crosswalk  |  Every station in both datasets  |  NOT_RECORDED  | None recorded | None recorded |  PENDING  |  Obtain an effective-dated crosswalk covering all 66 Godavari and 30 Krishna audit identities.  |
|  6  |  Name/code/coordinate reuse, renaming, movement, replacement, station history  |  Every station in both datasets  |  NOT_RECORDED  | None recorded | None recorded |  PENDING  |  Obtain station-history and identity-reuse rules with effective dates.  |
|  7  |  Coordinate CRS/datum, order, source, accuracy, represented feature  |  Every station in both datasets  |  NOT_RECORDED  | None recorded | None recorded |  PENDING  |  Obtain authoritative coordinate metadata; do not assume WGS 84.  |
|  8  |  River, tributary, basin, reach, upstream/downstream and Halia Vijaywada blank `River`  |  Both datasets  |  NOT_RECORDED  | None recorded | None recorded |  PENDING  |  Obtain station-level hydrological mapping and explain 8,593 missing Krishna `River` values.  |
|  9  |  State/district code/name version and historical boundary changes  |  Every station in both datasets  |  NOT_RECORDED  | None recorded | None recorded |  PENDING  |  Obtain the authoritative administrative-code reference and applicable version.  |
|  10  |  Meaning of `Data Acquisition Time`  |  Both datasets  |  NOT_RECORDED  | None recorded | None recorded |  PENDING  |  Determine whether this is measurement, logger, transmission/receipt, or ingestion time.  |
|  11  |  Timezone/offset, daylight-saving, synchronization, precision, late corrections  |  Both datasets and station periods  |  NOT_RECORDED  | None recorded | None recorded |  PENDING  |  Obtain product-specific timezone and clock/correction conventions; do not infer from application configuration.  |
|  12  |  Expected sampling schedules, outages, telemetry/publication delay, filtering  |  Each station and effective period  |  NOT_RECORDED  | None recorded | None recorded |  PENDING  |  Obtain expected cadence and outage/coverage records; compare to observed gaps without filling them.  |
|  13  |  Meaning of missing timestamps and station commissioning/decommissioning  |  Each station and effective period  |  NOT_RECORDED  | None recorded | None recorded |  PENDING  |  Obtain operating periods and a definition of whether absence means no measurement, no transmission, inactivity, or filtering.  |
|  14  |  Water-level field quantity, units, method, sign, stage/elevation/depth semantics  |  Both datasets  |  NOT_RECORDED  | None recorded | None recorded |  PENDING  |  Obtain the authoritative field definition and unit for these exact historical resources.  |
|  15  |  Negative/extreme values, sentinel rules, validation and cited examples  |  Both datasets and cited rows  |  NOT_RECORDED  | None recorded | None recorded |  PENDING  |  Obtain provider interpretation for cited rows; do not label them erroneous without evidence.  |
|  16  |  `RL_of_zeroGauge` and `MeanSeaLevel` definitions and units  |  Both datasets and each station  |  NOT_RECORDED  | None recorded | None recorded |  PENDING  |  Obtain formal field definitions and explain zero/default-looking values.  |
|  17  |  Vertical datum, benchmark/reference, conversion, survey epoch, validity, comparability  |  Both datasets and each station  |  NOT_RECORDED  | None recorded | None recorded |  PENDING  |  Obtain gauge-specific datum evidence and valid conversion/comparability rules.  |
|  18  |  Meaning of zero values in reference fields  |  Both datasets  |  NOT_RECORDED  | None recorded | None recorded |  PENDING  |  Obtain confirmation whether zero is valid, a placeholder, default, or another encoding.  |
|  19  |  Observation QC/status availability, categories, rules, sentinels  |  Both datasets  |  NOT_RECORDED  | None recorded | None recorded |  PENDING  |  Obtain a QC/status dictionary or provider confirmation that no observation-level flag exists.  |
|  20  |  Repeated station/time rows, revisions, corrections, versioning, authoritative reading  |  Both datasets and cited repeated rows  |  NOT_RECORDED  | None recorded | None recorded |  PENDING  |  Obtain a duplicate/revision policy and source-record traceability.  |
|  21  |  Meaning and temporal scope of `Is_DischargeDataAvailable`  |  Both datasets  |  NOT_RECORDED  | None recorded | None recorded |  PENDING  |  Obtain field definition and confirm its relationship, if any, to water-level quality.  |
|  22  |  Exact license instrument/version or written permission and attribution  |  Both datasets  |  NOT_RECORDED  | None recorded | None recorded |  PENDING  |  Obtain authoritative terms and required attribution text.  |
|  23  |  Permission for retention, research, derivatives, publication, redistribution  |  Both datasets  |  NOT_RECORDED  | None recorded | None recorded |  PENDING  |  Confirm each intended use explicitly; document any restrictions.  |
|  24  |  Commercial, access, embargo, attribution, or additional approval conditions  |  Both datasets  |  NOT_RECORDED  | None recorded | None recorded |  PENDING  |  Obtain written conditions and any required approvals.  |

## Evidence intake and review instructions

1. **Do not send automatically.** A project member must verify the proposed contact and recipient office, review the draft, complete sender details, and send it manually if approved.
2. Save the sent request, dispatch date, recipient, delivery/receipt evidence, attachments, and any ticket/reference ID in an appropriately access-controlled project record. Record only what actually occurred; keep any credential or personal contact data out of public reports.
3. Preserve the provider's original response and attachments unchanged in a controlled evidence location. Record the original filename, received date, sender identity/role as stated, channel, resource/version scope, and SHA-256 where practical. Do not copy sensitive personal data into this public-facing tracker.
4. Add a dated tracker entry for every response: question ID, affected dataset/stations/time period, exact evidence file/reference, source/issuer, reviewer, review date, decision, rationale, conflicts/limitations, and next action. Link evidence; do not paraphrase in a way that changes the provider's meaning.
5. A response, email signature, public-access label, CSV header, application setting, or plausible value is not by itself sufficient. Confirm that evidence is authoritative, versioned, and applies to the exact export and station/period in question.
6. If evidence is incomplete or contradictory, keep the affected readiness field `UNRESOLVED`, set the tracker decision to `INSUFFICIENT` or `CONFLICTING`, and record the precise follow-up question.
7. Change a readiness field to `CONFIRMED` only after a human reviewer records the authoritative evidence reference and scope, and the evidence meets that field's `evidence_required` in the JSON gate. If relevant evidence establishes irrelevance, use `NOT_APPLICABLE` only with a documented justification and review reference.
8. Do not change the global normalization decision from `BLOCKED` until every blocking requirement is satisfied for both datasets and the complete station mapping, timestamp, units/datum, QC/duplicate, provenance, coverage, and reuse evidence has been reviewed.
9. After modifying the readiness JSON, validate it and have a second project reviewer check that every `CONFIRMED`/`NOT_APPLICABLE` status points to evidence and that no raw rows or existing processed outputs were changed.

## Change log

| Date | Change | Evidence/reviewer |
|---|---|---|
| 2026-10-28 | Tracker created. No provider response or evidence was recorded; contact remains unverified; both datasets remain blocked. | Documentation-only update; no provider contact made. |
