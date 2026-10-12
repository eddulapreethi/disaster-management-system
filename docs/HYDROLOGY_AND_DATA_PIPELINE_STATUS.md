# Hydrology and Data Pipeline Status

## Current status

**Flood inference: NOT READY and remains disabled.** The implementation preserves the existing prediction safety gate. Neither successful collection nor the presence of GIS/event data is treated as a trained model or validated prediction. The AI assistant and its provider, route, prompts, and UI were not changed.

| Component | Status | Evidence |
|---|---|---|
| Weather collection | Operational; observation readiness is evaluated independently | Open-Meteo observations and fetch timestamps are distinct; default poll interval is 300 seconds |
| CWC/NWDP collection | Fetch operational; measurements stale | Most recent provider checks succeeded, but both source maxima remained September 27, 2026 |
| GIS files | 7 of 7 pass structural/CRS/study-bbox checks | GeoJSON/GeoTIFF validation is exposed in `/api/data-readiness`; map integration is false |
| EM-DAT artifacts | Source/categorical manifests validate by content hash | Event history does not supply site-level environmental labels |
| Flood model/features | NOT READY | No model artifact, verified legacy feature semantics, or inference builder |
| Automatic prediction | Disabled | Readiness response says `automatic_prediction_enabled=false`; user-triggered ML inference remains gated |

## Hydrology source investigation

The collector calls the public NWDP CKAN `datastore_search` API at `https://nwdp.nwic.gov.in/api/3/action/datastore_search` using the configured official CWC resource IDs. An audit of the provider responses on **2026-10-11** found:

| Resource | Provider rows reported | Latest source observation | Stored maximum | Result |
|---|---:|---|---|---|
| Krishna-basin CWC river water level | 18,240 | 2026-09-27 21:30 UTC | Matched provider maximum | No observation within the six-hour threshold |
| Andhra Pradesh CWC rainfall | 723 | 2026-09-27 01:30 UTC | Matched provider maximum | No observation within the six-hour threshold |

The collector fetched the sources again on 2026-10-11 (latest recorded cycle at approximately 09:28 UTC), but found no observation newer than the stored maximum (`newer_observation_found=false`). At that check, the maxima were approximately 13.5 and 14.3 days old respectively, far beyond the configured six-hour freshness threshold. This is **source publication staleness**, not a local latest-row sort error or failed HTTP retrieval. The audit specifically compared the maximum parsed observation timestamp; provider `_id` order alone is not a safe observation-time ordering.

The resources describe hourly telemetry, but polling every five minutes cannot compel the provider to publish new measurements. Retry and pagination logic addresses transport/collection reliability, not source-side publication gaps. The collector records provider fetch outcome separately from observation age and reports successful checks with no new records as `SUCCESS_NO_NEW_DATA`. No missing or current measurements are fabricated. Discharge remains null because the water-level resource's availability flag does not contain a discharge measurement.

## Diagnostics and operational behavior

`GET /api/hydrology/status` reports per resource:

- provider resource ID; station ID/name; latest observation time and age;
- last successful fetch; declared source update cadence and configured per-source freshness threshold;
- collection status separately from measurement freshness;
- provider rows scanned, raw new rows, normalized new rows, inserted rows, duplicates, and parse errors;
- whether a timestamp newer than the stored source maximum was discovered and the latest error, if any.

`GET /api/data-readiness` includes weather/hydrology source status, GIS file validation, hash-checked historical event manifests and explicit feature/model/prediction gates. Both endpoints use the existing bearer-token authentication. The five-minute collector default is configurable through `HYDROLOGY_POLL_INTERVAL_SECONDS`; the global stale threshold defaults to six hours, with overrides `HYDROLOGY_CWC_KRISHNA_WATER_LEVEL_STALE_AFTER_HOURS` and `HYDROLOGY_CWC_ANDHRA_RAINFALL_STALE_AFTER_HOURS`. `NWDP_OBSERVATION_TIMEZONE` defaults to `Asia/Kolkata` for source timestamps that lack timezone metadata.

Hydrology HTTP retries are bounded, and only one collection cycle per source runs in a process. Use one Uvicorn worker because the scheduler is in-process. SQLite startup adds diagnostic columns without deleting existing collection state. PostgreSQL deployments must apply [`database/migrations/004_hydrology_collection_diagnostics.sql`](../database/migrations/004_hydrology_collection_diagnostics.sql) before deploying the reader/writer code. Validate database backup and migration behavior in staging first.

## Reproducible datasets

Run from the repository root with `DATABASE_URL` pointing to the intended database:

```powershell
python -m ml.preprocessing.export_environmental_snapshots
python -m ml.preprocessing.historical_disasters.clean_emdat
python -m ml.preprocessing.historical_disasters.filter_disasters
```

The observation exporter writes deterministic-order weather and hydrology CSV snapshots and SHA-256 manifests. Current measured outputs are recorded in [`DATA_ACQUISITION_AND_PREPARATION_REPORT.md`](./DATA_ACQUISITION_AND_PREPARATION_REPORT.md). EM-DAT category outputs also have manifests; the actual retrieval date is unknown because the supplied workbook does not record it. Dataset manifests distinguish source-file name dates from verified retrieval evidence.

The outputs are not a joined training dataset. Weather and hydrology observations are not aligned to event locations/times, and EM-DAT does not give local non-event conditions or a validated continuous probability target. The legacy 20-index features have no documented semantics, units, sources, or transformations. GIS layers are reference layers rather than verified model features; they currently are not rendered as static flood layers. No satellite imagery or derived flood products are present. These gaps are why the model remains NOT_READY.

## User-facing safety

Stored legacy scores and simulation values are labeled unverified/illustrative; recommendation copy clarifies it is general precautionary information, not a forecast or official warning. The stored-points API labels old values as `unverified_saved_record`. This pipeline does not trigger predictions. Official alerts and local authorities remain the source for operational warnings.
