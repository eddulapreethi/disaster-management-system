# Hydrology freshness and cursor design

## Summary

The hydrology collector uses a cursor based on the source `_id` field (`source_record_high_watermark`) rather than a timestamp. This is a valid approach only when the upstream source guarantees that `_id` is non-decreasing with observation time.

The current repository code is designed to keep collection status separate from freshness status:

- `state.source_record_high_watermark` tracks the newest seen `source_record_id`
- `state.last_observation_at` tracks the newest valid observation timestamp stored in the database
- `data_readiness_service.get_hydrology_status()` compares the latest observation time against the configured stale window

This is intentionally conservative. A successful request does not imply fresh data.

## Code evidence

The collector logic is in `backend/app/services/hydrology_service.py`.

Relevant functions:

- `_request_page()`
  - calls `https://nwdp.nwic.gov.in/api/3/action/datastore_search`
  - uses `limit`, `offset`, `sort=_id desc`, and `include_total=true`
- `_fetch_new_rows()`
  - scans pages sequentially
  - stops once the page minimum `_id` falls at or below the saved cursor
- `_collect_hydrology_cycle()`
  - updates `HydrologyCollectionState`
  - sets `source_record_high_watermark` to the newest source `_id`
  - keeps `last_observation_at` based on the newest valid observation timestamp
- `get_hydrology_status()` in `backend/app/services/data_readiness_service.py`
  - marks a source as `STALE` when `now - latest_observation_at > stale_after`
  - keeps collection result separate from freshness result

## Why this is correct for the observed state

The upstream dataset is public, and the code is not inventing new records. The collector checks the live source, finds no newer `_id` than the persisted cursor, and records the result as `SUCCESS_NO_NEW_DATA`.

Freshness is then computed from timestamp age:

- if the last valid observation is older than the configured threshold, the source is reported as `STALE`
- if the latest valid observation is missing or in the future, the source is reported as `ERROR` or `UNAVAILABLE`

This is exactly the intended behavior.

## Verification against the live provider

The investigation rechecked the public endpoint directly and compared it with the local database state.

The live provider data has a newest row with `_id` at the current watermark, and there is no higher `_id` beyond it. The local database state already reflects that watermark. The remaining issue is simply that the newest observation is older than the freshness window.

## Design conclusion

The cursor is a safe proxy for "no newer source row exists" for the current provider behavior, but it is not a freshness indicator. Freshness must always be derived from the observation timestamp, not the fetch success or cursor update.

Therefore:

- `SUCCESS_NO_NEW_DATA` means no new source row was found
- `STALE` means the newest valid observation is older than the allowable age
- a successful request does not imply fresh telemetry

No code change is warranted when the provider itself has no newer observations beyond the stored cursor and the timestamp age is outside the allowed window.
