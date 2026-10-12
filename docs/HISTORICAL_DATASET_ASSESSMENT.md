# Historical dataset assessment

## Scope and provenance

The six processed extracts under `ml/datasets/historical_data/processed/` are derived from the supplied EM-DAT workbook:

`ml/datasets/historical_disasters/EM-DAT/public_emdat_custom_request_2026-09-30_65676a52-2bac-4e9b-b454-70d54b055fa3.xlsx`

The workbook's EM-DAT Data sheet contains 10,902 event rows and 47 source columns, spanning start years 2000–2026, 220 countries, and 14 disaster-type categories. The workbook also contains an EM-DAT Info sheet. The source is an academic/research request and is subject to EM-DAT access terms; these files do not establish redistribution rights.

The reproducible inventory and aggregates are built by `python -m ml.preprocessing.historical_analytics`. The processor checks each extract, processed-input, and workbook SHA-256 against its manifest before aggregation. It does not edit the source workbook or extracts. Derived outputs are:

- `ml/datasets/historical_data/analytics/historical_analytics.json`
- `ml/datasets/historical_data/analytics/historical_analytics.manifest.json`

## Extract inventory

Coordinate counts require both latitude and longitude to be present and within geographic ranges. Missing-impact rates describe missing values in each processed extract.

| Extract | Rows | Start-date coverage | Countries | Valid coordinate pairs | Missing start date | Missing deaths | Missing total affected |
|---|---:|---|---:|---:|---:|---:|---:|
| Earthquakes | 707 | 2000-01-02–2026-08-14 | 94 | 680 (96.18%) | 0% | 34.09% | 2.97% |
| Floods | 4,291 | 2000-01-01–2026-08-26 | 181 | 1,006 (23.44%) | 6.64% | 26.66% | 9.62% |
| Glacial lake outburst floods | 8 | 2021-02-07–2025-07-07 | 5 | 0 (0%) | 0% | 12.50% | 50.00% |
| Landslides | 519 | 2000-01-19–2026-08-23 | 72 | 15 (2.89%) | 1.54% | 3.08% | 33.53% |
| Storms/cyclones | 2,929 | 2000-01-02–2026-11-10 | 190 | 115 (3.93%) | 2.19% | 25.40% | 25.64% |
| Wildfires | 356 | 2000-01-15–2026-08-26 | 66 | 0 (0%) | 24.44% | 48.31% | 21.91% |
| **Total extract rows** | **8,810** | | | | | | |

The extracts contain 8,810 distinct event IDs; no event IDs overlap across these six files. Each extract has zero exact duplicate rows and zero repeated event IDs within the extract. Extract row totals and distinct-event counts are both reported; they are not silently conflated.

The source event-type aggregation counts 4,291 Flood records, 707 Earthquakes, 2,929 Storms, 504 wet mass movements, 15 dry mass movements, 356 Wildfires, and 8 Glacial lake outburst floods. Categories are EM-DAT classifications, not local flood occurrence labels.

## Data quality and analytical limits

The extracts retain all 50 processed fields. Relevant fields include event identifier, disaster type, country/location, reported coordinates, start/end dates, deaths, affected people and reported damage. The date bounds above use valid `start_date`; the processor separately reports invalid/missing dates and coordinate coverage.

Across the six extracts, 1,816 rows have valid coordinate pairs and 6,994 do not. Location coverage is therefore inadequate for treating all event rows as point observations or aligning them to local weather/gauge series. Impact fields are incomplete; use the per-extract missingness percentages above rather than interpreting reported sums as complete totals.

The current descriptive aggregation reports non-missing source values only: 6,492 records have a reported death value (sum 1,210,351 people), 7,369 have total affected (sum 3,021,353,903 people), and 3,157 have total damage (sum 3,673,624,250.92 in the source's thousand-US-dollar units). These are sums of reported figures with incomplete coverage—not complete global totals, validated loss estimates, or prediction targets.

EM-DAT records are event and impact reports. They do not provide complete surveillance of event-free sites, validated local inundation observations, continuous river-threshold targets, or a time-aligned environmental feature series. Missing event records must not be interpreted as negative examples. This data supports descriptive analytics and historical event counts with classification and coverage limitations; it does not support training or validating a flood predictor on its own.

## Reproducibility snapshot

The current generated analytics manifest reports:

- Transformation: `emdat-historical-analytics-v1`
- Source rows scanned: 8,810
- Distinct event IDs: 8,810
- Rejected rows: 0
- Output SHA-256: `24f1d441122dd96e0257a029321a8c297b4af68dae506a33232207c475a6e012`

Rebuild and verify the manifest with:

```powershell
D:\MajorProject\.venv\Scripts\python.exe -m ml.preprocessing.historical_analytics
```

The output hash can change if source inputs or transformation code change; the manifest records current input and output hashes.
