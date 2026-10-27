# Historical analytics status

**Audit date:** 2026-10-27

Historical analytics are descriptive summaries of the six supplied, hash-validated EM-DAT extracts. They do not represent complete event surveillance, local flood labels, environmental measurements, probabilities, or forecasts.

## Verified snapshot

The six files contain 8,810 rows and 8,810 distinct, non-missing EM-DAT `DisNo.` identifiers. All six manifests, processed CSV hashes, source workbook hashes, and processed-input hashes validate. There are no duplicate event IDs within an extract, exact duplicate rows, missing event IDs, or `DisNo.` overlaps between these extracts.

| Extract | Rows / unique IDs | Valid start dates | Missing dates | Future dates | End before start | Valid coordinates / rows |
|---|---:|---:|---:|---:|---:|---:|
| Earthquakes | 707 / 707 | 707 | 0 | 0 | 1 | 680 / 707 (96.18%) |
| Floods | 4,291 / 4,291 | 4,006 | 285 | 0 | 0 | 1,006 / 4,291 (23.44%) |
| Glacial lake outburst floods | 8 / 8 | 8 | 0 | 0 | 0 | 0 / 8 (0.00%) |
| Landslides | 519 / 519 | 511 | 8 | 0 | 0 | 15 / 519 (2.89%) |
| Storms/cyclones | 2,929 / 2,929 | 2,865 | 64 | 1 | 2 | 115 / 2,929 (3.93%) |
| Wildfires | 356 / 356 | 269 | 87 | 0 | 0 | 0 / 356 (0.00%) |
| **Total** | **8,810 / 8,810** | **8,366** | **444** | **1** | **3** | **1,816 / 8,810 (20.61%)** |

Coordinates use the complete extract row count as the denominator. The 1,816 valid pairs are within latitude `[-90, 90]` and longitude `[-180, 180]`; 6,994 rows do not have a valid pair. No supplied rows have an out-of-range pair or a partial pair. Missing coordinates are not inferred.

The event-type counts from the source `disaster_type` field are:

| EM-DAT source disaster type | Events |
|---|---:|
| Flood | 4,291 |
| Storm | 2,929 |
| Earthquake | 707 |
| Mass movement (wet) | 504 |
| Wildfire | 356 |
| Mass movement (dry) | 15 |
| Glacial lake outburst flood | 8 |

`landslides.csv` contains the two distinct EM-DAT mass-movement types. Glacial lake outburst flood remains its own source classification; no classification is rewritten as a general flood.

## Impact coverage

Totals count only valid, non-negative source reports across the unique event IDs. Missing and invalid fields are not treated as zero. The source extracts contain zero explicit zero values for these three impact fields.

| Source field | Reported values / 8,810 events | Coverage | Sum | Unit |
|---|---:|---:|---:|---|
| `total_deaths` | 6,492 | 73.69% | 1,210,351 | people |
| `total_affected` | 7,369 | 83.64% | 3,021,353,903 | people |
| `total_damage_'000_us$` | 3,157 | 35.83% | 3,673,624,250.92 | thousand source-reported US dollars |

Damage uses the EM-DAT `Total Damage ('000 US$)` source field, not the adjusted-damage field. No currency conversion, inflation adjustment, or completeness claim is applied. Full per-extract coverage and file hashes are in [EMDAT_DATA_QUALITY_REPORT.md](./EMDAT_DATA_QUALITY_REPORT.md).

## Date and yearly-count correction

The processed `start_date` is constructed from EM-DAT `Start Year`, `Start Month`, and `Start Day`. The previous analytics grouped every row directly by `start_year`; that included rows without a complete date and an internally contradictory future record. The current yearly grouping uses valid `start_date`, excludes dates after the explicitly reported `as_of_date`, and excludes a record if its end date precedes its start date. All exclusions remain in the extract and in hazard/country source counts; reasons and counts are returned in `summary.year_aggregation`.

At the 2026-10-27 audit date, 8,363 unique events qualify for yearly aggregation. There are 444 missing start dates and three end-before-start records; one of those three is the single future start date, so reason counts overlap. The three source chronology conflicts are listed in the data-quality report.

## Year counts after correction

| Start-date year | Events | Start-date year | Events | Start-date year | Events |
|---:|---:|---:|---:|---:|---:|
| 2000 | 282 | 2009 | 283 | 2018 | 266 |
| 2001 | 279 | 2010 | 323 | 2019 | 342 |
| 2002 | 330 | 2011 | 264 | 2020 | 368 |
| 2003 | 302 | 2012 | 265 | 2021 | 396 |
| 2004 | 311 | 2013 | 296 | 2022 | 334 |
| 2005 | 350 | 2014 | 267 | 2023 | 365 |
| 2006 | 331 | 2015 | 328 | 2024 | 345 |
| 2007 | 353 | 2016 | 292 | 2025 | 331 |
| 2008 | 296 | 2017 | 314 | 2026 | 150 |

## Country ranking

The API returns objects (`{country, count}`) in an array. The top ten, ordered by count descending and then country name case-insensitively with a stable original-name tie-break, are China 635; United States of America 623; Indonesia 381; Philippines 371; India 369; Viet Nam 199; Japan 169; Mexico 159; Afghanistan 152; and Brazil 151. Blank country names are excluded from this ranking; the current six extracts have no missing country values.

The previous frontend treated the array as a mapping. `Object.entries()` yielded an index and an object, and the object’s `toLocaleString()` produced `[object Object]`. The UI now renders each `country` and `count` from the actual API response shape and has a non-fabricating empty state.

## Readiness and limitations

- Historical analytics depends on the EM-DAT manifests and files, not current CWC freshness or a trained model.
- Historical analytics remains descriptive-ready only; flood-prediction model/features/inference readiness remains unchanged and `NOT_READY`.
- The source workbook states EM-DAT/CRED/UCLouvain, version `2026-09-18`, and file creation `30 Sep 2026 08:35:20 UTC`. Its filename date is not treated as proof of actual retrieval date.
- The EM-DAT files are supplied for an academic/research request. The project does not claim that access terms grant redistribution rights.
- The original source workbook and six source extracts were read only and were not regenerated or modified.

Detailed schemas, source hashes, validation evidence, impact/date/coordinate diagnostics, and implementation details are in [EMDAT_DATA_QUALITY_REPORT.md](./EMDAT_DATA_QUALITY_REPORT.md) and [HISTORICAL_ANALYTICS_API.md](./HISTORICAL_ANALYTICS_API.md).
