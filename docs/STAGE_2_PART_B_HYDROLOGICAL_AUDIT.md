# Stage 2 Part B: Hydrological Data Audit

- **Overall status:** WARNING
- **Audit date (UTC):** 2026-10-28T06:20:37+00:00
- **Script:** `D:\MajorProject\disaster-management-system\ml\preprocessing\audit_hydrological_observations.py`
- **Command:** `python -m ml.preprocessing.audit_hydrological_observations --json-report D:\MajorProject\disaster-management-system\docs\STAGE_2_PART_B_HYDROLOGICAL_AUDIT.json --markdown-report D:\MajorProject\disaster-management-system\docs\STAGE_2_PART_B_HYDROLOGICAL_AUDIT.md`

Status definitions: PASS means the stated technical check completed; WARNING means quality, provenance, or scientific questions remain; FAIL means a required check failed or the audit did not complete; NOT_CHECKED means no evidence was available or the check was outside this audit.

This is data preparation only. A successful script run does not establish a validated flood prediction model or readiness for hydraulic modelling.

Rows are streamed. Duplicate keys are stored in a temporary on-disk SQLite database, not in an unbounded Python set; the database is deleted at process exit.

## godavari_water_level_2021_2025.csv

- **File:** `D:\MajorProject\disaster-management-system\ml\datasets\hydrological\raw\godavari_water_level_2021_2025.csv`
- **Audit execution / data quality:** PASS / WARNING
- **Size:** 185715692 bytes
- **Encoding / delimiter:** UTF-8 with optional BOM / `,`
- **Rows / stations:** 1055737 / 66
- **Observed timestamp range:** 2021-01-01T00:00 to 2025-12-29T19:00
- **Timestamp convention:** source timestamps are timezone-naive; no timezone inferred
- **Timestamp parse failures:** 0
- **Malformed CSV rows:** 0
- **Rows missing station identity:** 0
- **Important missing values:** `{"River Water Level Telemetry Hourly (meter)": 10894}`
- **Exact duplicate rows:** 0
- **Repeated station/timestamp records:** 122
- **Repeated station/timestamp records with a different water level:** 18
- **Source-order timestamp regressions:** 0
- **Intervals:** 848676 exactly 60 minutes; 128070 shorter; 78803 longer
- **Water-level range (source column labeled metres):** -673.0 to 2583.0; 5630 negative values require review
- **Distinct river/basin metadata:** `["Godavari"]` / `["Godavari"]`
- **Filename-to-basin metadata comparison:** True (not independently verified)
- **Stations with inconsistent metadata:** 0
- **Station states supplied in metadata:** `["Andhra Pradesh", "Chhattisgarh", "Madhya Pradesh", "Maharashtra", "Odisha", "Telangana"]`
- **Invalid numeric values:** `{}`
- **Non-finite numeric values:** `{}`

### Warnings

- 122 repeated station/timestamp records
- 5630 negative water-level values require review
- 10894 water-level values are missing

### Largest timestamp gaps (top 5)

- Kosagumda (Bhaskel) (Odisha): 2021-07-20T04:00 to 2024-07-22T23:00 (26371.0 hours)
- Wairagarh (Maharashtra): 2024-07-18T09:00 to 2025-12-17T21:00 (12420.0 hours)
- Kumhari (Madhya Pradesh): 2023-04-13T04:00 to 2024-08-20T07:00 (11883.0 hours)
- Nizamsagar Reservoir (Telangana): 2024-08-09T13:30 to 2025-11-15T10:30 (11109.0 hours)
- Koida (Andhra Pradesh): 2022-08-10T04:00 to 2023-10-12T04:00 (10272.0 hours)

## krishna_water_level_2021_2025.csv

- **File:** `D:\MajorProject\disaster-management-system\ml\datasets\hydrological\raw\krishna_water_level_2021_2025.csv`
- **Audit execution / data quality:** PASS / WARNING
- **Size:** 74000976 bytes
- **Encoding / delimiter:** UTF-8 with optional BOM / `,`
- **Rows / stations:** 451445 / 30
- **Observed timestamp range:** 2021-01-01T00:00 to 2025-12-30T05:00
- **Timestamp convention:** source timestamps are timezone-naive; no timezone inferred
- **Timestamp parse failures:** 0
- **Malformed CSV rows:** 0
- **Rows missing station identity:** 0
- **Important missing values:** `{"River Water Level Telemetry Hourly (meter)": 611}`
- **Exact duplicate rows:** 0
- **Repeated station/timestamp records:** 43
- **Repeated station/timestamp records with a different water level:** 4
- **Source-order timestamp regressions:** 0
- **Intervals:** 368289 exactly 60 minutes; 46143 shorter; 36940 longer
- **Water-level range (source column labeled metres):** -990.33 to 1602.237; 9311 negative values require review
- **Distinct river/basin metadata:** `["Krishna"]` / `["Krishna"]`
- **Filename-to-basin metadata comparison:** True (not independently verified)
- **Stations with inconsistent metadata:** 0
- **Station states supplied in metadata:** `["Andhra Pradesh", "Karnataka", "Maharashtra", "Tamil Nadu", "Telangana"]`
- **Invalid numeric values:** `{}`
- **Non-finite numeric values:** `{}`

### Warnings

- 43 repeated station/timestamp records
- 9311 negative water-level values require review
- 611 water-level values are missing

### Largest timestamp gaps (top 5)

- Shimoga (Karnataka): 2021-11-03T08:00 to 2023-12-18T06:00 (18598.0 hours)
- Keesara (Andhra Pradesh): 2023-03-03T11:00 to 2024-09-01T04:00 (13145.0 hours)
- Koyna (Maharashtra): 2022-05-02T10:30 to 2023-10-10T03:30 (12617.0 hours)
- Ujjani Reservoir (Maharashtra): 2022-05-02T10:30 to 2023-10-09T15:30 (12605.0 hours)
- MAHISHI (Karnataka): 2021-09-11T21:00 to 2022-12-03T00:00 (10731.0 hours)

## Normalization

**NOT_CHECKED** — No verified site mapping or confirmed source timezone was supplied. Do not infer stable gauge IDs, timezones, quality flags, or vertical datums.

## Unresolved provenance and scientific limitations

- **source_authenticity:** NOT_CHECKED
- **reuse_license:** NOT_CHECKED
- **provider_metadata_snapshot:** NOT_CHECKED
- **stable_station_identifier:** NOT_CHECKED
- **measurement_datum:** NOT_CHECKED
- **data_dictionary_and_quality_flags:** NOT_CHECKED

## Recommended next steps

1. Obtain authoritative station IDs and provider documentation for field semantics and QC.
2. Confirm source timezone, units, vertical datum, coordinates, basin assignment, and reuse terms.
3. Review reported gaps, duplicates, outliers, and metadata inconsistencies with the data provider.
4. Only then prepare a normalized derivative with source-row traceability and explicit quality flags.

## Commands

- `python -m ml.preprocessing.audit_hydrological_observations --json-report D:\MajorProject\disaster-management-system\docs\STAGE_2_PART_B_HYDROLOGICAL_AUDIT.json --markdown-report D:\MajorProject\disaster-management-system\docs\STAGE_2_PART_B_HYDROLOGICAL_AUDIT.md`
