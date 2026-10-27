# EM-DAT data quality report

**Audit date and date-validation cutoff:** 2026-10-27
**Project:** DisasterGuard AI
**Scope:** the six category CSVs and manifests actually consumed by the historical analytics pipeline. The original workbook was inspected read-only.

## Provenance and source integrity

All six category manifests point to this supplied workbook:

`ml/datasets/historical_disasters/EM-DAT/public_emdat_custom_request_2026-09-30_65676a52-2bac-4e9b-b454-70d54b055fa3.xlsx`

Its SHA-256 is `24f511cdf8dd1900c4124a2244e643f9940ce6c5a4c56f02c9630f6473992587`. The workbook contains sheets `EM-DAT Data` and `EM-DAT Info`; the data sheet has 10,902 rows and 47 columns. The information sheet identifies EM-DAT/CRED/UCLouvain, version `2026-09-18`, and file creation `Wed, 30 Sep 2026 08:35:20 UTC`. The source filename includes `2026-09-30`, but neither the filename nor file-creation metadata proves the actual retrieval date. The category manifests correctly leave `retrieval_date` unknown.

The six output CSVs are UTF-8 CSVs with 50 columns: the 47 cleaned source fields plus derived `start_date`, `end_date`, and `event_date`. All six manifests validate: CSV row counts, dataset hashes, validation hashes, source workbook hashes, and `emdat_cleaned.csv` input hashes match. The processed-input SHA-256 recorded by the manifests is `6b1a76e5893645870dfca143dda161a76139b61d4e9e90ab694dc38f6a602b32`.

| Extract | CSV | Rows | Manifest | CSV SHA-256 |
|---|---|---:|---|---|
| Earthquakes | `ml/datasets/historical_data/processed/earthquakes.csv` | 707 | VALIDATED | `890fa425f8b750bc4413db6fd43a8f4902f3078920ae32d00d679c7dbc6cf475` |
| Floods | `ml/datasets/historical_data/processed/floods.csv` | 4,291 | VALIDATED | `2d402e10fb087c44fd6def03117a81487fbd927cac8f0f1a88cf2e4c554c6998` |
| Glacial lake outburst floods | `ml/datasets/historical_data/processed/glacial_lake_outburst_floods.csv` | 8 | VALIDATED | `ba89f662ed07921b870f28e88f1a47954165c95bf60700166127d786a24d9e17` |
| Landslides | `ml/datasets/historical_data/processed/landslides.csv` | 519 | VALIDATED | `ec3eb4103a492add99a814cd21f11f1c0a28bd81613d5295fcdb806acfc5bd1a` |
| Storms/cyclones | `ml/datasets/historical_data/processed/storms_cyclones.csv` | 2,929 | VALIDATED | `867bdd88ba4d94b75afe2d56ec605315413a051869b51c2daed73c36d844fa19` |
| Wildfires | `ml/datasets/historical_data/processed/wildfires.csv` | 356 | VALIDATED | `188cea5bd5b2a4a64e6e5d4d55d24a73517bd46464bdb7215aa2582505eeb5ab` |

The original workbook and category CSVs were not rewritten. Category selection comes from `ml/preprocessing/historical_disasters/filter_disasters.py`: Earthquake, Flood, Glacial lake outburst flood, Storm, both Mass movement (wet) and Mass movement (dry), and Wildfire. Other rows in the 10,902-row source sheet are not part of these six extracts.

## Schema and field types

The common processed columns, in source order, are:

`disno.`, `historic`, `classification_key`, `disaster_group`, `disaster_subgroup`, `disaster_type`, `disaster_subtype`, `external_ids`, `event_name`, `iso`, `country`, `subregion`, `region`, `location`, `origin`, `associated_types`, `ofda_bha_response`, `appeal`, `declaration`, `aid_contribution_'000_us$`, `magnitude`, `magnitude_scale`, `latitude`, `longitude`, `river_basin`, `start_year`, `start_month`, `start_day`, `end_year`, `end_month`, `end_day`, `total_deaths`, `no._injured`, `no._affected`, `no._homeless`, `total_affected`, `reconstruction_costs_'000_us$`, `reconstruction_costs,_adjusted_'000_us$`, `insured_damage_'000_us$`, `insured_damage,_adjusted_'000_us$`, `total_damage_'000_us$`, `total_damage,_adjusted_'000_us$`, `cpi`, `admin_units`, `gadm_admin_units`, `entry_date`, `last_update`, `start_date`, `end_date`, `event_date`.

Relevant inferred types are: `disno.`/classification/country/date strings; year/month/day and reported count values integer-like numeric strings; coordinates and magnitude numeric; damage may be fractional (the storms/cyclones `total_damage_'000_us$` values infer as number). Coordinate columns are `unknown` for extracts where all values are missing. Types are inferred from actual non-missing values, not asserted as a formal source type system.

`start_date` and `end_date` are derived by `clean_emdat.py` from their respective year/month/day fields. `event_date` equals the derived `start_date`. The analysis retains the source `disaster_type` classification and does not infer hazard type from filenames.

## Event identifiers, duplicates, countries, and classification

| Extract | Rows | Unique non-missing `DisNo.` | Missing IDs | Repeated ID rows | Exact duplicate rows | Countries | Missing countries |
|---|---:|---:|---:|---:|---:|---:|---:|
| Earthquakes | 707 | 707 | 0 | 0 | 0 | 94 | 0 |
| Floods | 4,291 | 4,291 | 0 | 0 | 0 | 181 | 0 |
| Glacial lake outburst floods | 8 | 8 | 0 | 0 | 0 | 5 | 0 |
| Landslides | 519 | 519 | 0 | 0 | 0 | 72 | 0 |
| Storms/cyclones | 2,929 | 2,929 | 0 | 0 | 0 | 190 | 0 |
| Wildfires | 356 | 356 | 0 | 0 | 0 | 66 | 0 |
| **Total** | **8,810** | **8,810** | **0** | **0** | **0** | **not additive** | **0** |

Here, “repeated ID rows” means later rows repeating a non-empty ID within an extract; “exact duplicate rows” compares all fields. These are separate measures. The current extracts have no `DisNo.` overlap between files. `DisNo.` is used as the EM-DAT event identifier; the aggregation counts an identified event once across extracts and still reports any overlap rather than deleting source rows. There is no overlap requiring a source-conflict policy for this snapshot.

The source `disaster_type` field yields the event counts below. The landslides file contains two different source types, and GLOF is not silently folded into Flood:

| Source classification | Rows/events |
|---|---:|
| Flood | 4,291 |
| Storm | 2,929 |
| Earthquake | 707 |
| Mass movement (wet) | 504 |
| Wildfire | 356 |
| Mass movement (dry) | 15 |
| Glacial lake outburst flood | 8 |

## Start/end date quality

| Extract | Parseable start dates | Missing start dates | Invalid start dates | Future start dates as of 2026-10-27 | Parseable end dates | Missing end dates | Invalid end dates | End before start |
|---|---:|---:|---:|---:|---:|---:|---:|
| Earthquakes | 707 | 0 | 0 | 0 | 707 | 0 | 0 | 1 |
| Floods | 4,006 | 285 | 0 | 0 | 4,025 | 266 | 0 | 0 |
| Glacial lake outburst floods | 8 | 0 | 0 | 0 | 8 | 0 | 0 | 0 |
| Landslides | 511 | 8 | 0 | 0 | 510 | 9 | 0 | 0 |
| Storms/cyclones | 2,865 | 64 | 0 | 1 | 2,866 | 63 | 0 | 2 |
| Wildfires | 269 | 87 | 0 | 0 | 268 | 88 | 0 | 0 |
| **Total** | **8,366** | **444** | **0** | **1** | **8,384** | **426** | **0** | **3** |

All 8,366 parsed start dates match the corresponding source `start_year`. No impossible calendar dates were found in the processed date fields. The three end-before-start chronology conflicts were checked against the supplied workbook’s `EM-DAT Data` values and remain unmodified:

| `DisNo.` | Source start date | Source end date | Finding |
|---|---|---|---|
| `2026-0221-IDN` | 2026-04-02 | 2026-03-02 | End precedes start |
| `1995-0275-NPL` | 2026-11-10 | 1995-11-11 | Future start and end precedes start |
| `1988-0424-VEN` | 2026-09-11 | 1988-09-11 | End precedes start |

For `1995-0275-NPL`, the workbook itself contains `Start Year=2026`, `Start Month=11`, `Start Day=10`, `End Year=1995`, `End Month=11`, `End Day=11`; it is not a transformation-only discrepancy. The start is after the audit date and after the workbook file-creation timestamp reported in `EM-DAT Info`. This is a verified source inconsistency; its intended corrected date is unknown, so it is flagged rather than repaired. The other two rows have the same kind of source-level chronology contradiction. No record is silently removed from source, hazard, or country totals.

Yearly analytics use `start_date`, not `start_year` as a fallback. Only 8,363 unique IDs with a valid start date on/before the audit date and no end-before-start conflict are included. 444 events lack a full start date; one is future; three have reversed date ranges. The future event is also one of the three reversed-date events, so the reason counts overlap. The previous all-row `start_year` series summed to 8,810; the corrected date-eligible series sums to 8,363.

## Coordinate quality

The denominator for each coverage percent is every row in that extract. A valid pair requires both values present, finite, and within world bounds.

| Extract | Valid pairs / all rows | Coverage | Missing latitude | Missing longitude | Partial pair rows | Invalid/out-of-range rows |
|---|---:|---:|---:|---:|---:|---:|
| Earthquakes | 680 / 707 | 96.18% | 27 | 27 | 0 | 0 |
| Floods | 1,006 / 4,291 | 23.44% | 3,285 | 3,285 | 0 | 0 |
| Glacial lake outburst floods | 0 / 8 | 0.00% | 8 | 8 | 0 | 0 |
| Landslides | 15 / 519 | 2.89% | 504 | 504 | 0 | 0 |
| Storms/cyclones | 115 / 2,929 | 3.93% | 2,814 | 2,814 | 0 | 0 |
| Wildfires | 0 / 356 | 0.00% | 356 | 356 | 0 | 0 |
| **Total** | **1,816 / 8,810** | **20.61%** | **6,994** | **6,994** | **0** | **0** |

The same row can be missing both coordinates, so missing latitude and missing longitude counts are not additive. Zero latitude/longitude is valid when actually present. No coordinate is inferred from country, locality, or description.

## Impact fields, units, and coverage

The used columns are source `Total Deaths` → `total_deaths` (people), `Total Affected` → `total_affected` (people), and `Total Damage ('000 US$)` → `total_damage_'000_us$` (thousand source-reported US dollars). The pipeline does not use the separate `Total Damage, Adjusted ('000 US$)` field for this summary and makes no inflation or currency conversion.

Each cell below gives usable non-negative reports / extract rows. A usable explicit zero, if present, would count as a report; missing values are not zero. Across the six current files, there are no invalid numeric strings, negative values, or explicit zeros in these three used fields.

| Extract | Death reports / rows | Affected reports / rows | Damage reports / rows |
|---|---:|---:|---:|
| Earthquakes | 466 / 707 | 686 / 707 | 311 / 707 |
| Floods | 3,147 / 4,291 | 3,878 / 4,291 | 1,212 / 4,291 |
| Glacial lake outburst floods | 7 / 8 | 4 / 8 | 2 / 8 |
| Landslides | 503 / 519 | 345 / 519 | 55 / 519 |
| Storms/cyclones | 2,185 / 2,929 | 2,178 / 2,929 | 1,439 / 2,929 |
| Wildfires | 184 / 356 | 278 / 356 | 138 / 356 |
| **Total** | **6,492 / 8,810** | **7,369 / 8,810** | **3,157 / 8,810** |

| Impact | Report coverage | Sum of reported values | Unit |
|---|---:|---:|---|
| Deaths | 73.69% | 1,210,351 | people |
| Total affected | 83.64% | 3,021,353,903 | people |
| Total damage | 35.83% | 3,673,624,250.92 | thousand source-reported US dollars |

The totals are not complete global totals. A missing impact value stays missing and has no contribution to the reported-value sum. Impacts are aggregated once per unique `DisNo.`; because current extracts have no cross-file ID overlap, there is no duplicate impact to reconcile in this snapshot.

## Analytics and source terms

The corrected year series and top-ten country ranking are recorded in [HISTORICAL_ANALYTICS_STATUS.md](./HISTORICAL_ANALYTICS_STATUS.md). API field definitions and a response example are in [HISTORICAL_ANALYTICS_API.md](./HISTORICAL_ANALYTICS_API.md).

The manifests say the source is subject to the supplied EM-DAT academic/research request access terms. No redistribution right is inferred. Do not redistribute the source workbook or extracted records without checking the applicable terms.

Original workbook and source extract files were not edited; only the analytics implementation, dashboard presentation, tests, and generated derived analytics snapshot were changed.
