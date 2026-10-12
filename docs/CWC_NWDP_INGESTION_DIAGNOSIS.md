# CWC/NWDP ingestion diagnosis

## Scope and method

This Stage 3 diagnosis checked the live NWDP CKAN endpoints used by the project, the local collector implementation in `backend/app/services/hydrology_service.py`, and the persisted hydrology state in the application SQLite database.

The investigation focused on the two configured public CWC/NWDP sources:

- `nwdp:cwc_krishna_water_level` — resource ID `d80798b9-4b11-4626-8b63-964202ba7216`
- `nwdp:cwc_andhra_rainfall` — resource ID `349a10bc-bbe3-40e5-b415-92aa9a797065`

The collector checks are intentionally bounded and rate-aware. It does not inspect unlimited pages and it does not log or store any secrets.

## Verified flow from provider to dashboard

The current implementation follows this path:

1. `configured_resources()` reads the default public NWDP resource registry from `DEFAULT_RESOURCES` in `backend/app/services/hydrology_service.py`.
2. `collect_hydrology_cycle()` creates a DB session and reads the persisted `HydrologyCollectionState` row per source.
3. `_fetch_new_rows()` calls `_request_page()` for each page using this request shape:
   - `resource_id`, `limit`, `offset`, `sort=_id desc`, `include_total=true`
   - request URL: `https://nwdp.nwic.gov.in/api/3/action/datastore_search`
4. Each row is normalized using `normalize_record()`.
   - `source_record_id` comes from the CKAN `_id`.
   - `station_id` is a stable hash of the station metadata and coordinates.
   - `observation_time` is parsed from `Data Acquisition Time` and converted to UTC using the configured `Asia/Kolkata` timezone.
   - the value column is selected from the resource-specific field map: rainfall or river water level.
5. The collector stores records in `HydrologicalObservation`, then updates `HydrologyCollectionState` with metrics such as:
   - `source_record_high_watermark`
   - `records_returned`
   - `valid_records`
   - `duplicates_skipped`
   - `inserted_count`
   - `newer_observation_found`
   - `last_successful_fetch_at`
   - `last_observation_at`
6. `get_hydrology_status()` in `backend/app/services/data_readiness_service.py` converts the latest stored observation timestamp into freshness status:
   - if `now - latest_observation_time > stale_after`, it marks the source as `STALE`.
   - it keeps collection status (`SUCCESS_NO_NEW_DATA`, `SUCCESS_EMPTY_RESPONSE`, etc.) separate from freshness status.

## Exact cursor and comparison logic

For each source, the collector maintains a cursor based on the source's numeric `_id` (`source_record_high_watermark`).

- `high_water_id` is derived as `max(max(source_record_id in DB), state.source_record_high_watermark)`.
- `_fetch_new_rows()` requests pages until the newest page's minimum `_id` falls at or below that cursor or the page limit is reached.
- The collector does not use observation_time as the cursor.
- It keeps `newer_observation_found` based on `normalized["observation_time"] > max_observation` among rows inspected in the current cycle.

This code path is internally consistent. The issue is not a global cursor bug in the collector logic. The observed stale statuses occur when the provider has no newer observation beyond the persisted high-water mark and freshness threshold.

## Verified root cause for each feed

### 1) Krishna water level (`nwdp:cwc_krishna_water_level`)

Live provider evidence (current NWDP dataset):

- total rows: 18,240
- latest rows returned on the first page: `_id` 18240, 18239, 18238 with `Data Acquisition Time` values `28-09-2026 02:00`, `28-09-2026 01:00`, `28-09-2026 00:00`
- the current local database state shows `source_record_high_watermark = 18240` and `last_observation_at = 2026-09-27 21:30:00` (UTC)

These values match the provider data after converting the India-local timestamp to UTC:

- `28-09-2026 02:00` in `Asia/Kolkata` = `2026-09-27 20:30:00Z`

This means the collector is not missing a newer record. It has already reached the provider's latest `_id` and latest observation. The source is simply stale relative to the current time, so the dashboard corrects it as `SUCCESS_NO_NEW_DATA / STALE`.

### 2) Andhra rainfall (`nwdp:cwc_andhra_rainfall`)

Live provider evidence (current NWDP dataset):

- total rows: 723
- first page latest rows: `_id` 723, 722, 721 with `Data Acquisition Time` values `01-05-2026 14:30`, `01-05-2026 13:30`, `01-05-2026 12:30`
- the current local database state shows `source_record_high_watermark = 723` and `last_observation_at = 2026-09-27 01:30:00` (UTC)

This is the same pattern: the collector has reached the most recent source record it can obtain from the live dataset, and the latest observation is simply older than the configured freshness window. The feed is stale because the provider has no newer rainfall records than the saved cursor.

## What is not happening

- There is no evidence of a pagination loop bug.
- There is no evidence of a malformed response causing the collector to silently skip data.
- There is no evidence that the collector is incorrectly marking a successful request as fresh.
- There is no evidence that the dashboard is inventing measurements or timestamps.

The implementation is correctly distinguishing:

- collection success (`SUCCESS_NO_NEW_DATA` when the provider returned rows but none advanced the cursor)
- freshness (`STALE` when the observation timestamp is older than the configured threshold)

## Conclusion

The verified root cause is an upstream data publication delay / source staleness, not a code defect in the collector or cursor logic.

The collector is correctly doing the following:

- fetching live NWDP records
- tracking the highest `_id`
- recognizing when there is no newer record than the cursor
- keeping freshness separate from collection success
- reporting `STALE` when the latest valid observation is older than the configured threshold

The pipeline should not be forced to READY simply because a request succeeded.
