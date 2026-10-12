# Hydrology freshness diagnostics

**Checked:** 2026-10-11 (UTC)  
**Provider:** National Water Data Portal / National Water Informatics Centre (NWDP/NWIC), public CKAN API.

## Official resources and response structure

The collector uses the documented CKAN actions:

- [CKAN `datastore_search` API](https://nwdp.nwic.gov.in/api/3/action/datastore_search)
- [CWC Krishna river-level resource metadata](https://nwdp.nwic.gov.in/api/3/action/resource_show?id=d80798b9-4b11-4626-8b63-964202ba7216)
- [CWC Andhra Pradesh rainfall resource metadata](https://nwdp.nwic.gov.in/api/3/action/resource_show?id=349a10bc-bbe3-40e5-b415-92aa9a797065)

`datastore_search` returns a JSON object with `success`, `result.records`, `result.total`, pagination links and field metadata. The collector requests `resource_id`, `limit`, `offset`, `sort=_id desc`, and `include_total=true`; default page size is 1,000 and default per-cycle ceiling is 64 pages. Initial collection walks the ordered pages. Later cycles scan from offset zero until a row at/below the saved maximum `_id` is reached. A cycle that hits its page ceiling without reaching the cursor fails and does not advance it.

Returned records contain `_id`, station name/agency/state/district, latitude/longitude, `Data Acquisition Time`, and a source-specific value. Water-level measurements use `River Water Level Telemetry Hourly (meter)`; rainfall uses `Telemetry Hourly Rainfall (mm)`. The water-level feed's `Is_DischargeDataAvailable` is a flag, not a discharge measurement, and is not stored as one.

Station identity is derived from agency, station, administrative codes and coordinates because these response rows do not expose a stable official station ID. Timestamp strings without offsets are interpreted in `NWDP_OBSERVATION_TIMEZONE` (default `Asia/Kolkata`) and normalized to UTC. Data is deduplicated by source resource, derived station ID and observation time, with database uniqueness constraints as a second safeguard.

## Live and persisted-data verification

Read-only NWDP CKAN requests on 2026-10-11 checked each resource's descending-ID page and exact station-filtered response. The resource metadata modification time is **not** evidence of a new measurement:

| Resource | `datastore_search` total | Newest returned row with `_id desc` | Measurement value |
|---|---:|---|---|
| Krishna water level (`d80798b9-4b11-4626-8b63-964202ba7216`) | 18,240 | `_id=18240`, Yadgir; `28-09-2026 02:00` source local time | 351.953 m |
| Andhra Pradesh rainfall (`349a10bc-bbe3-40e5-b415-92aa9a797065`) | 723 | `_id=723`, VONI; `01-05-2026 14:30` source local time | 0.5 mm |

The exact station-filtered results were:

| Station | Highest source `_id` for station | Latest source observation | Latest stored observation | Result |
|---|---:|---|---|---|
| Mantralayam (water level) | 9,886 | `28-09-2026 03:00` local (`2026-09-27T21:30:00Z`), 307.981 m | `2026-09-27T21:30:00Z`, 307.981 m | Source and stored values match; no later published station row |
| Koida (rainfall) | 337 | `27-09-2026 07:00` local (`2026-09-27T01:30:00Z`), 0.5 mm | `2026-09-27T01:30:00Z`, 0.5 mm | Source and stored values match; no later published station row |

The read-only local SQLite database confirms the Krishna cursor and maximum stored source ID are both **18,240**, and the rainfall cursor and maximum stored source ID are both **723**. The corresponding stored observation totals were 17,234 and 723; the lower Krishna count reflects station/time duplicate suppression and does not indicate a missing tail at the cursor. The successful fetches in the local diagnostic state occurred at `2026-10-11 15:09:44Z` and `15:09:45Z`; those fetch times do not make the old observations fresh.

This is provider-side publication staleness, not a demonstrated collector cursor or pagination failure: both saved cursors equal the highest IDs currently returned by their resource endpoints, and station-filtered source rows match the latest stored station observations. For Mantralayam and Koida, neither endpoint supplied a genuinely newer observation during this check. The latest observations are outside the configured six-hour freshness window. No source response proves what CWC may hold upstream but has not published to NWDP.

The next lower-ID rows in the descending pages had earlier acquisition times, consistent with the collector's pagination assumption in the sampled pages. `resource_show` reported `datastore_contains_all_records_of_source_file: false`, so the public CKAN datastore may not mirror every source-file row. No independent source-file comparison was treated as proof of newer observations.

## Collector diagnostics and interpretation

The collector records scanned rows, unique rows newer than the numeric `_id` cursor, valid rows, inserted observations, duplicate station/time pairs, parser failures, page count, cursor before/after, latest observation timestamp in scanned source rows, latest stored observation timestamp, and fetch time. The per-run summary log keeps fetch time separate from observation time. Repeated source IDs across pages are discarded by stable `_id`; counts of provider rows returned still include repeated rows.

Observation freshness is calculated from the latest stored `observation_time`; the fetch timestamp is tracked separately. A successful response that has rows but no IDs above the cursor is `SUCCESS_NO_NEW_DATA`, while freshness remains `STALE` when the stored observation exceeds the freshness window. This accurately describes the observed condition; it does not claim successful source publication.

The status response distinguishes:

- `SUCCESS_WITH_NEW_DATA`: records beyond the saved cursor were processed and at least one was inserted.
- `SUCCESS_NO_NEW_DATA`: rows were returned but none had an ID beyond the saved cursor.
- `SUCCESS_EMPTY_RESPONSE`: the provider successfully returned no rows.
- `SUCCESS_DUPLICATES_ONLY`: new source rows were valid but their station/time observations were already stored.
- `PARSE_ERRORS`: one or more source rows failed validation; the collector reports the error.
- `ERROR`: network, HTTP, response-shape, configuration, or other collection error.

Each is separate from `freshness_status` (`READY`, `STALE`, `UNAVAILABLE`, or `ERROR`). A successful fetch may coexist with stale observations; a new row may also carry an old `Data Acquisition Time` if publication is delayed. The frontend now explains empty responses, unchanged rows, new data, duplicates and parse failures distinctly.

## Established findings and remaining uncertainty

- The collector is not repeatedly requesting an unspecified default ordering: it explicitly requests `_id desc`, follows `offset` pages and uses the persisted numeric high-water mark. Numeric comparison is performed after converting `_id` to `int`.
- Duplicate observations are filtered in memory and protected by database unique constraints. A database constraint conflict aborts and rolls back the current source transaction rather than silently counting it as success.
- A newly inserted source row with an old observation time does not make readiness fresh. A delayed row with a larger `_id` is retained, while freshness remains based on its source time.
- Rows with malformed timestamps are reported as parse errors and skipped so a bad row cannot block newer IDs. The cursor may advance past such a malformed row; the error is visible, but automatic replay of that row is not implemented.
- Strict `_id` high-water ingestion assumes newly published records receive higher IDs. If the provider later inserts a record with a lower ID, that record may be missed. No evidence from the sampled API establishes how the provider handles backfills or ID reassignment.
- The public metadata says the datastore does not contain all source-file rows. The collector cannot recover source records absent from the CKAN datastore.
- Persistence failure rolls back inserted observations and leaves the previously committed cursor unchanged. A regression test verifies that retry can resume from that prior cursor.
- No official per-client rate limit was established in this review. Current polling checks both configured resources every 300 seconds by default and uses bounded retries; operators should follow any provider terms/policies and increase the interval if required.

## Verification and safety gates

Regression coverage verifies mixed numeric IDs, descending and ascending ordering within a page, multi-page fetches, repeated IDs across pages, same-station/timestamp duplicate handling, malformed timestamps and measurements, stale source timestamps, no-new-ID cursor stability, resuming/idempotent polling, and cursor preservation after a failed database commit. See `backend/tests/test_hydrology_service.py`.

Validation results: `pytest backend\tests\test_hydrology_service.py -q` passed (**21 passed**); `pytest backend\tests ml -q` passed (**148 passed, 1 skipped, 28 subtests passed**). The full run emitted three existing SHAP deprecation warnings. `git diff --check` passed; Git reported only a pre-existing LF-to-CRLF warning for `frontend/src/pages/Simulation.jsx`.

No hydrology change alters the ML model readiness check or prediction readiness gate. Prediction remains `NOT_READY` until a genuine compatible trained artifact, verified feature contract, and runtime feature builder are available. A Digital Twin score of zero remains unrelated to measured real-world flood risk.

## Recommended remediation

No fabricated or inferred observations were added. Keep the UI stale until source timestamps advance. The confirmed root cause for the dashboard's two stale values is that NWDP's public resources have not published a later observation for either station; the collector cursor is already at each resource's current maximum source ID. For operational use, confirm the provider's publication schedule, backfill/ID guarantees, and timezone with NWDP/CWC, compare the full resource or an independently authorized source against stored records, and only adjust polling/query strategy based on documented provider behavior. Do not loosen freshness thresholds to make old telemetry appear current.
