# Historical analytics API

## Route and dependencies

The authenticated `GET /historical-data/analytics` route (under the frontend API base URL) is implemented in `backend/app/api/historical_data.py`. It computes results from manifests and files in the historical-data directories. It does not query hydrology/weather observations, a trained model, or prediction readiness. A manifest/source validation failure is returned as an explicit dataset error; partial valid results are retained when one or more extracts fail.

The endpoint currently uses a typed dictionary rather than a separate Pydantic response model. Consumers should treat the shape below as the route contract.

## Response fields

- `status`: `READY`, `PARTIAL`, or `ERROR`.
- `as_of_date`: ISO date used for future-date validation and date-based yearly counts.
- `analytics_version`: transformation version.
- `dataset_inventory`: one record per manifest, including failed manifests.
  - Valid entries include `name`, `dataset_file` (basename only), `manifest_validation`, `rows`, `unique_event_count`, `columns`, inferred `data_types`, provenance, validation hashes, event classifications, missing-value counts/percentages, duplicate statistics, date diagnostics, coordinate diagnostics, per-impact coverage, and warnings.
  - Failed entries include dataset name, expected basename, `manifest_validation: ERROR`, and an error. File paths are not returned.
- `summary`: aggregate row/event counts, `events_by_year`, `events_by_disaster_type`, `events_by_country`, reported impact aggregates, year-grouping metadata, and cross-extract/data-quality diagnostics.
- `validation_errors`: dataset-specific errors for failed manifests.
- `capabilities` and `limitations`: descriptive scope and explicit non-prediction/source-term caveats.

The response preserves the previously used `summary` keys, including `source_rows_across_extracts`, `unique_event_ids`, `event_ids_present_in_multiple_extracts`, `events_by_year`, `events_by_disaster_type`, `events_by_country`, and `reported_impacts`. Dataset `path`/`manifest` fields and the historical-readiness `source_workbook` path have been replaced with basenames to avoid exposing local workspace paths. Existing frontend consumers do not rely on those paths.

## Country ranking contract

`summary.events_by_country` is an array, not a country-to-count object:

```json
[
  {"country": "China", "count": 635},
  {"country": "United States of America", "count": 623}
]
```

Countries are ranked by event count descending. Ties are ordered by `country.casefold()` ascending, then the original source country string ascending for deterministic output. Blank or missing country names are excluded; their count is reported separately in data-quality metadata. Counts represent distinct non-missing EM-DAT event IDs assigned to the source country. The frontend renders the array objects by their `country` and `count` properties.

## Date, coordinate, and impact semantics

- Yearly counts use valid `start_date` values, not a fallback from `start_year`. Records with missing/invalid start dates, future start dates relative to `as_of_date`, or an end date earlier than the start date are excluded from the year series only. The source rows remain in the extracts and other source event/category/country totals. `summary.year_aggregation` reports each exclusion reason and a distinct total; reason counts may overlap.
- Coordinate coverage is `rows_with_both_valid_coordinates / coordinate_coverage_denominator`, where the denominator is all rows in that dataset. Latitude and longitude bounds are inclusive: `[-90, 90]` and `[-180, 180]`.
- `impact_coverage` and `reported_impacts` distinguish missing, invalid, negative, and explicit-zero values. Only valid, non-negative source reports contribute to sums. Units are source units and are not converted.
- Event counts by hazard use the row's EM-DAT `disaster_type`; extract file names are not used to rewrite the hazard field.
- Cross-extract records are reported as overlapping when their `DisNo.` appears in multiple extracts. Row totals remain row totals; unique-event summaries count an ID once.

## Error behavior and partial results

- No manifests: the endpoint raises a validation error, surfaced as HTTP 503 with an explicit message.
- Some valid and some failed manifests: response status is `PARTIAL`, valid extracts are summarized, and `validation_errors` identifies failed extracts.
- No valid extracts: response status is `ERROR`, with zero aggregate counts and the failed datasets listed.
- Successful historical processing remains independent of stale CWC readings and ML readiness. It does not change model status or enable inference.

The analytics cache is keyed by a fingerprint of relevant file paths, sizes, and modification timestamps and expires after 30 seconds. Ordinary file changes alter the fingerprint and rebuild validation/analytics immediately; the expiry bounds reuse for filesystem changes not reflected in those metadata values. The rebuild verifies source workbook, processed input, CSV, and manifest hashes before returning validated results.
