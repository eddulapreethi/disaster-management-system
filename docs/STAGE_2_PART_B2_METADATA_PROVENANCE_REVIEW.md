# Stage 2 Part B.2: Hydrological Metadata and Provenance Review

## Scope and evidence boundary

This review uses the two unchanged raw CSVs, the Stage 2 Part B audit, and documentation already present in this repository. No new provider request or external documentation lookup was made. It does not authenticate the exact local files, grant reuse rights, establish a validated observation product, or establish readiness for hydraulic modelling.

The full source header, per-station metadata values, counts, and yearly coverage recorded by the audit are in [`STAGE_2_PART_B_HYDROLOGICAL_AUDIT.json`](./STAGE_2_PART_B_HYDROLOGICAL_AUDIT.json). The readable aggregate audit is [`STAGE_2_PART_B_HYDROLOGICAL_AUDIT.md`](./STAGE_2_PART_B_HYDROLOGICAL_AUDIT.md).

Status meanings in this review:

- **CONFIRMED IN FILE** means the value or field is present in the local CSV, not that an external authority verified its truth.
- **CONFIRMED IN REPOSITORY EVIDENCE** means an existing project document records that evidence; it may concern a catalog or separate live resource rather than these exact files.
- **INFERRED** means suggested by naming, formatting, or consistency but not authoritative.
- **UNKNOWN** means the available evidence does not establish the fact.

## Metadata review table

| Field/question | Godavari file evidence | Krishna file evidence | Status and limitation |
|---|---|---|---|
| Publisher / agency | `Agency` is `CWC` on all 66 station identities | `Agency` is `CWC` on all 30 station identities | **CONFIRMED IN FILE**, not source authentication. Existing [source audit documentation](./FLOOD_DATA_IMPORT_GUIDE.md) records CWC as publisher of NWDP catalog resources, but does not bind these exact files to a resource ID or retrieval. |
| Stable physical gauge ID | No provider station ID column. `SlNo` is a serial-like field; `Station` is a name. Identity used for audit is case-folded station name + state and district codes. | Same | **UNKNOWN.** Do not treat station name, `SlNo`, or an internally generated key as a provider gauge ID. |
| Station names | Present for all 66 audit identities | Present for all 30 audit identities | **CONFIRMED IN FILE** as labels only; names are not proven unique physical gauges. |
| Coordinates | Decimal-looking `Latitude`/`Longitude`; one coordinate pair per station in the audited rows. Range: lat 16.93833333–22.32472222, lon 73.80333333–82.51194444. | Same structure; range: lat 13.69722222–18.07, lon 73.75–80.62111111. | **CONFIRMED IN FILE** as numeric values. Interpreting them as decimal geographic coordinates is **INFERRED** from the field names and values. CRS, coordinate reference realization, survey/source, accuracy, and whether coordinates identify gauge structures or approximate locations are **UNKNOWN**. Do not assume WGS 84 solely from column names. |
| Administrative location | State, district, tehsil/block/village labels and `State LGD Code` / `District LGD Code` fields are present. State labels span Andhra Pradesh, Chhattisgarh, Madhya Pradesh, Maharashtra, Odisha, Telangana. | Same fields; state labels span Andhra Pradesh, Karnataka, Maharashtra, Tamil Nadu, Telangana. | **CONFIRMED IN FILE** as supplied strings/codes; external code-to-boundary mapping and current administrative validity are **UNKNOWN**. |
| Basin / river | All station metadata says `River=Godavari`, `Basin=Godavari`. | All 30 identities say `Basin=Krishna`; 29 say `River=Krishna`. The `River` field is blank in 8,593 rows for Halia Vijaywada. | **CONFIRMED IN FILE** as source metadata only. Treating the basin as independently verified from filename agreement would be an unsupported **INFERENCE**. The missing Krishna river field needs provider explanation. |
| Acquisition timestamp | `Data Acquisition Time`; observed source text parses as `DD-MM-YYYY HH:MM`. Actual dataset-wide range is 2021-01-01 00:00 to 2025-12-29 19:00. | Same field and format; range 2021-01-01 00:00 to 2025-12-30 05:00. | Field and values **CONFIRMED IN FILE**; timezone, UTC offset, clock convention, and whether this means measurement time, telemetry receipt time, or database acquisition time are **UNKNOWN**. Existing collector code uses `Asia/Kolkata`, but [the import guide](./FLOOD_DATA_IMPORT_GUIDE.md) explicitly requires confirmation for each product. That code is not proof for these exports. |
| Water-level field and units | `River Water Level Telemetry Hourly (meter)` | Same | The header declares metres, and repository documentation records a metre unit in NWDP catalog metadata. That unit is **DECLARED**, not independently verified for these exact historical files. Negative values and extreme magnitudes need provider semantics and QC. |
| Meaning of negative readings | 5,630 negative numeric values; observed minimum -673.0 | 9,311 negative numeric values; observed minimum -990.33 | **UNKNOWN.** Could not distinguish a valid local gauge reference, sentinel/error encoding, sign convention, or bad record without a data dictionary and datum definition. No negative value was removed. |
| `RL_of_zeroGauge` | Present on all station records; one distinct supplied value per station; 9 stations have value 0. | Same; 10 stations have value 0. | Header/value **CONFIRMED IN FILE**; meaning, units, reference surface, validity dates, and relationship to measured level are **UNKNOWN**. |
| `MeanSeaLevel` | Present on all station records; one distinct supplied value per station; 12 stations have value 0. | Same; 15 stations have value 0. | Header/value **CONFIRMED IN FILE**; whether this is an elevation, datum offset, reference level, or another provider field is **UNKNOWN**. It must not be interpreted as a verified vertical datum or used to convert levels. |
| Vertical datum / reference elevation | No explicit datum identifier column. | Same | **UNKNOWN.** No compatible common vertical reference is established between gauges or between these fields and the measured values. |
| Quality flags / measurement status | No per-observation QC/quality flag column. | Same | **UNKNOWN.** `Is_DischargeDataAvailable` is not a water-level quality flag and does not establish a water-level observation's validity. No status meaning or sentinel dictionary was found for these CSVs. |
| Operating periods | Rows exist from 2021 through 2025 in the file as a whole; station-by-year counts are listed in the JSON audit. | Same | Per-station first/last record dates describe only records present, not installation, commissioning, decommissioning, outages, or official operating periods. Those are **UNKNOWN**. |
| Frequency / coverage | Header includes “Hourly,” but the audit measured 848,676 60-minute, 128,070 shorter, and 78,803 longer intervals between consecutive unique timestamps. 30-minute intervals are frequent; substantial multi-month/year gaps occur. | 368,289 60-minute, 46,143 shorter, and 36,940 longer intervals; 30-minute intervals are frequent; substantial multi-month/year gaps occur. | “Hourly” is a **DECLARED label**, not consistent observed cadence or completeness. No gap is interpolated. Detailed largest gaps and common intervals are in the audit report. |
| Source resource, retrieval, and authenticity | Local filename and contents only; no adjacent source metadata manifest was supplied. | Same | **UNKNOWN for these exact files.** Existing project documentation records CWC/NWDP public catalog metadata for other resource evidence, including a live resource named 2026–2030 and historical Subernarekha listings; it does not identify these 2021–2025 basin exports as an authenticated, complete source snapshot. |
| Attribution / license / reuse | Not included in CSV headers or a local manifest. | Same | **UNKNOWN.** Existing documentation says NWDP catalog metadata reported public access / `isopen: true` and license title “Other (Open),” which is not a specific standard license or permission for redistribution. Do not redistribute or infer an unrestricted reuse right. |

### Station summary for review

| Dataset | Distinct audit identities | Supplied states | Supplied river / basin values | Supplied coordinates present | Missing metadata of note |
|---|---:|---|---|---:|---|
| Godavari | 66 | Andhra Pradesh; Chhattisgarh; Madhya Pradesh; Maharashtra; Odisha; Telangana | Godavari / Godavari | 66 of 66 identities | No missing station identity, coordinates, state, district, river, basin, or agency in the audit. |
| Krishna | 30 | Andhra Pradesh; Karnataka; Maharashtra; Tamil Nadu; Telangana | River: Krishna on 29 identities; basin: Krishna on 30 | 30 of 30 identities | Halia Vijaywada has blank `River` for 8,593 rows; no missing station identity, coordinates, state, district, basin, or agency in the audit. |

The complete 66- and 30-station listing, including names, administrative codes, coordinate strings, supplied river/basin/agency, `RL_of_zeroGauge`, `MeanSeaLevel`, counts, and records-by-year, is in the `stations` array of the machine-readable audit. Its coordinate fields remain unverified for CRS and positional accuracy.

## Conflicting records and suspicious values

Line references below are physical CSV line numbers (line 1 is the header); `SlNo` is copied from the raw row. These are examples, not an exhaustive listing. The raw rows remain unchanged.

### Repeated station/time with different values

| File | Raw row references | Station and timestamp | Water-level values as stored | Other supplied reference fields |
|---|---|---|---|---|
| Godavari | lines 126530 (`SlNo=126529`) and 126531 (`SlNo=126530`) | Bhatpalli, 03-03-2021 17:30 | 185.015 vs 166.848 | `RL_of_zeroGauge=156.0000`; `MeanSeaLevel=170.42`; coordinates 19.32972222, 79.50416667. |
| Godavari | lines 130684 (`SlNo=130683`) and 130685 (`SlNo=130684`) | Bhatpalli, 30-09-2021 08:00 | 194.15 vs 184.073 | Same supplied station reference values and coordinates as above. |
| Godavari | lines 130808 (`SlNo=130807`) and 130809 (`SlNo=130808`) | Bhatpalli, 06-10-2021 01:00 | 177.101 vs 185.335 | Same supplied station reference values and coordinates as above. |
| Krishna | lines 20336 (`SlNo=20335`) and 20337 (`SlNo=20336`) | Bawapuram, 09-10-2021 11:00 | 271.339 vs 271.338 | `RL_of_zeroGauge=270.2450`; `MeanSeaLevel=280.00`; coordinates 15.88250000, 77.95722222. |
| Krishna | lines 138331 (`SlNo=138330`) and 138332 (`SlNo=138331`) | Madhira, 24-10-2021 18:00 | 44.503 vs 44.504 | `RL_of_zeroGauge=44.5000`; `MeanSeaLevel=52.00`; coordinates 16.91805556, 80.35888889. |
| Krishna | lines 179776 (`SlNo=179775`) and 179777 (`SlNo=179776`) | Mantralayam, 06-10-2021 07:00 | 309.339 vs 309.183 | `RL_of_zeroGauge=306.0000`; `MeanSeaLevel=0`; coordinates 15.94000000, 77.42000000. |

The audit found **122** repeated station/timestamp records in Godavari (18 with differing water-level text) and **43** in Krishna (4 with differing water-level text). Exact duplicate full rows: zero in both. The source does not identify whether repeated readings are revisions, retransmissions, parallel measurements, or erroneous duplicates; do not choose a “winner” without provider rules.

### Extreme and negative values

| File | Raw row / SlNo | Station and timestamp | Water-level value | Supplied `RL_of_zeroGauge` / `MeanSeaLevel` |
|---|---|---|---:|---|
| Godavari minimum | line 942909 / `SlNo=942908` | Sriram Sagar Reservoir, 28-07-2024 08:00 | -673.0 | 0.0000 / 307.85 |
| Godavari maximum | line 883229 / `SlNo=883228` | Sangam (Murredu), 31-07-2022 17:00 | 2583.0 | 50.0000 / 52.00 |
| Godavari negative run | lines 345567, 345570–345571 / `SlNo=345566`, `345569`–`345570` | Jaikwadi Dam, 18–19-05-2022 | -561.8, -565.8, -563.8 | 0.0000 / 0 on the shown rows |
| Krishna minimum | line 318148 / `SlNo=318147` | Prakasam Barrage, 28-06-2022 20:00 | -990.33 | 13.7300 / 0 |
| Krishna maximum | line 49767 / `SlNo=49766` | Bhadra Reservoir, 29-12-2022 02:30 | 1602.237 | 0.0000 / 0 |
| Krishna negative run | lines 4149–4151 / `SlNo=4148`–`4150` | Almatti Reservoir, 20-05-2022 | -403, -358, -345 | 0.0000 / 0 on the shown rows |

These are **review flags, not findings that the measurements are false**. The source's units, vertical reference, sentinel rules, and validation status are unresolved. The review does not discard or reinterpret them.

### Gaps and irregular observations

The file header's “Hourly” wording is not consistent with only hourly intervals: common intervals include 30 minutes, and shorter or longer intervals were measured in both basins. The largest observed unique-timestamp gaps include:

- Godavari: Kosagumda (Bhaskel), 2021-07-20 04:00 to 2024-07-22 23:00 (**26,371 hours**).
- Krishna: Shimoga, 2021-11-03 08:00 to 2023-12-18 06:00 (**18,598 hours**).

Other large gaps are listed in the Part B report. A station's first/last record is not an authoritative operating period; a gap is not evidence of no flooding or no measurement unless coverage and outage semantics are supplied. No timestamps or readings were interpolated.

## Provider-clarification checklist

Request a written response tied to the exact export/resource IDs and versions. Ask the provider to answer each item rather than relying on field-name interpretation:

1. **File provenance:** Identify the authoritative CWC/NWDP resource, API/resource ID, export generation time, retrieval date, exact coverage, query/filter, and source checksum for each local CSV. Confirm whether the file is a complete export or a partial/page-limited extract and whether the advertised 2021–2025 years are source coverage.
2. **Stable gauge identity:** Provide the stable provider-approved gauge/station ID for every `Station` + state/district code + coordinate combination. Explain whether names/codes can be reused, renamed, moved, or shared, and provide station history/crosswalks.
3. **Coordinates:** Confirm coordinate order, CRS/datum (for example, whether WGS 84 is intended), coordinate source, precision/accuracy, and what physical feature the coordinate represents. Confirm station-location changes and their effective dates.
4. **Acquisition time:** Define `Data Acquisition Time`: measurement instant, logger time, transmission/receipt time, or database ingestion time. State timezone/offset, daylight-saving treatment if applicable, clock synchronization, timestamp precision, and handling of late corrections.
5. **Water-level field:** Confirm the physical quantity, exact unit, measurement method, sign convention, and whether values are gauge stage, elevation, depth, or another level. Explain negative and extreme values, including the cited source rows, and identify any sentinel values.
6. **Reference fields and vertical datum:** Define `RL_of_zeroGauge` and `MeanSeaLevel`, their units, geodetic/vertical datum, benchmark/reference elevation, sign and conversion equations, survey epoch, validity period, and how the measured water-level field relates to each. Explain zero or missing-looking values and whether values can be compared between stations.
7. **Quality and revision status:** Supply the observation-level QC/status flags or confirm none exist. Provide the data dictionary, validation rules, rejected/suspect/corrected status meanings, revision/version history, and rules for repeated station/timestamp records with different values. Explain which record (if any) is authoritative and how corrections are represented.
8. **Operation and completeness:** Supply commissioning/decommissioning and station relocation periods, expected sampling schedule by station and effective period, outage/telemetry coverage logs, and a definition of whether a missing timestamp means no observation, no transmission, or a filtered record.
9. **Hydrological and administrative mapping:** Confirm basin, river/reach/tributary, station's upstream/downstream context, and administrative code/name reference version. Explain the missing Krishna `River` values for Halia Vijaywada.
10. **Discharge flag:** Define `Is_DischargeDataAvailable`, including whether it applies to the station overall or a row/time period. Confirm it is not a water-level QC indicator.
11. **Attribution and reuse:** Identify the exact license instrument/version and terms for copying, retention, derivative products, publication, redistribution, and commercial use. If no standard license applies, provide written permission and required attribution.

## Decision

**Normalization cannot safely proceed for these two files yet.** The current normalizer requires a provider-reviewed station mapping and a source timezone; neither is established by authoritative evidence for these historical exports. Units/datum, quality rules, repeated-record resolution, exact resource provenance, and reuse conditions are also unresolved. Keep the raw files unchanged, do not overwrite existing processed outputs, and do not infer missing metadata or convert the timestamp to UTC based solely on the collector's configuration.

This is a provenance and metadata review only. It does not validate observations, produce flood labels or forecasts, or establish readiness for hydraulic modelling.
