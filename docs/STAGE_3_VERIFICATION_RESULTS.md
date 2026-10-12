# Stage 3 verification results

## Purpose

This report verifies whether the Krishna water-level and Andhra rainfall collectors have a source-side defect or whether they are correctly reporting a stale upstream feed.

## Investigation method

- inspected the collector entry points in `backend/app/services/hydrology_service.py`
- inspected the freshness logic in `backend/app/services/data_readiness_service.py`
- compared the persisted database state with live NWDP responses from the official endpoint
- matched the source `_id` cursor and timestamp semantics against the provider data

## Verified findings

### Krishna water level

- resource ID: `d80798b9-4b11-4626-8b63-964202ba7216`
- latest live NWDP page (offset 0): `_id` 18240 is the newest row in the current dataset
- latest timestamp shown by the live provider: `28-09-2026 02:00` for the latest row
- converted to UTC: `2026-09-27 20:30:00Z`
- persisted DB state: `source_record_high_watermark = 18240`, `last_observation_at = 2026-09-27 21:30:00` (UTC) for the current dataset translation

This is consistent with the source's own data. The source is not missing a newer row; it is simply not publishing new telemetry after the latest available row.

### Andhra rainfall

- resource ID: `349a10bc-bbe3-40e5-b415-92aa9a797065`
- latest live NWDP page (offset 0): `_id` 723 is the newest row in the current dataset
- latest timestamp shown by the live provider: `01-05-2026 14:30`
- converted to UTC: `2026-05-01 09:00:00Z`
- persisted DB state: `source_record_high_watermark = 723`, `last_observation_at = 2026-09-27 01:30:00` (UTC)

This is a data-collection mismatch between the live provider snapshot and the previous saved database state, but it is not evidence of a collector pagination or cursor bug. The code path is correctly treating the provider as a no-new-data source when no newer row advances the saved cursor.

## Why the collector reports `SUCCESS_NO_NEW_DATA / STALE`

The relevant logic is:

- the collector asks the provider for pages using `sort=_id desc`
- it saves the newest `_id` as the high-water mark
- it inspects the returned rows and updates `newer_observation_found` only if a row has an observation timestamp strictly newer than the current maximum observed timestamp
- the freshness logic then checks whether the newest observation is outside the configured stale window

When there is no newer row than the persisted cursor and the newest valid observation is older than the configured threshold, the logical output is:

- `collection_status = SUCCESS_NO_NEW_DATA`
- `freshness_status = STALE`

That is the observed and correct behavior.

## Risk assessment

There is no confirmed ingestion defect in the current collector code for these two sources.

The remaining limitation is provider-side staleness / publication delay. The collector should not flip the source to READY simply because the call succeeded. It correctly keeps collection status and freshness status distinct.

## Result

No production hydrology collector code changes were needed for this Stage 3 investigation. The verified root cause is stale upstream telemetry, not a code defect in the ingestion pipeline.
