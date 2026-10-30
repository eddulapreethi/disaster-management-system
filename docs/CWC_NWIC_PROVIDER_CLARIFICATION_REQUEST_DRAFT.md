# Draft: CWC/NWIC Hydrological Data Clarification Request

**Draft status:** For project-team review only. **Not sent.** No email or external request has been made.

**Proposed recipient:** `rdcdte-cwc@nic.in`  
**Recipient basis:** This address is recorded as the source contact in the repository's existing [CWC/NWDP import guide](./FLOOD_DATA_IMPORT_GUIDE.md), based on catalog metadata reviewed by the project. Verify the current contact and the appropriate CWC/NWIC office before sending.

**Suggested subject:** Clarification and data-use terms for CWC/NWDP Godavari and Krishna water-level CSV exports (2021–2025)

---

Dear CWC/NWIC Data Team,

We are reviewing two CWC water-level CSV files for an academic disaster-management data-preparation project:

- `godavari_water_level_2021_2025.csv`
- `krishna_water_level_2021_2025.csv`

The files contain fields including `SlNo`, `Station`, `Agency`, state and district labels/codes, `Latitude`, `Longitude`, `River`, `Basin`, `Is_DischargeDataAvailable`, `RL_of_zeroGauge`, `MeanSeaLevel`, `Data Acquisition Time`, and `River Water Level Telemetry Hourly (meter)`. We have not modified the source observations. The filenames and row contents alone do not establish the export resource, completeness, measurement semantics, quality status, or reuse permission.

Could you please provide written clarification and, where possible, the authoritative data dictionary, station registry/crosswalk, source resource identifiers, metadata snapshots, and applicable license or permission document addressing the questions below?

### 1. Dataset provenance and coverage

1. What are the exact NWIC/NWDP package, dataset, resource, and version identifiers corresponding to each file?
2. Are these files official CWC/NWIC exports? Please confirm export generation time, retrieval period, query/filter, source checksum if available (or explicitly state if none is available), and the authoritative download/API endpoint.
3. Are the CSVs complete exports for their stated scope, or are they partial, filtered, paginated, or otherwise truncated? What exact period and stations should they contain?
4. Does the filename's “2021–2025” label represent intended coverage or verified complete coverage? Please provide the source's coverage statement.

### 2. Station identity and location

5. Please provide the stable, provider-approved physical gauge/station ID for every station row, together with an authoritative crosswalk to the supplied station name, state/district codes, coordinates, and river/basin.
6. Can station names, codes, or coordinates be reused, renamed, moved, or assigned to a replacement gauge? Please provide station history and effective dates where relevant.
7. What coordinate reference system/datum, coordinate order, source, and accuracy apply to `Latitude` and `Longitude`? Do the coordinates identify the gauge structure, a nearby location, or an administrative representative point?
8. Please confirm the river, tributary, basin, reach, and upstream/downstream context for each station. In the Krishna file, `River` is blank for Halia Vijaywada in 8,593 rows while the `Basin` field says Krishna; please explain the intended river assignment.
9. Please identify the version/effective date of the state and district codes/names and explain any historical boundary or code changes.

### 3. Timestamp semantics and cadence

10. What event does `Data Acquisition Time` represent: measurement instant, logger timestamp, telemetry transmission/receipt, or database ingestion time?
11. What timezone and UTC offset apply? Are daylight-saving changes relevant? What clock synchronization, timestamp precision/rounding, and late-arrival or correction conventions apply?
12. The header includes “Hourly,” but the exports contain shorter/longer intervals and large gaps. What cadence is expected for each station and period? Are there planned seasonal schedules, outages, telemetry failures, publication delays, or filtering?
13. What does an absent timestamp mean: no measurement, failed transmission, unavailable record, station inactivity, or another status? Please provide operating/commissioning/decommissioning periods and coverage/outage evidence.

### 4. Water-level and reference-field semantics

14. Please define `River Water Level Telemetry Hourly (meter)`: physical quantity, exact unit, measurement method, sign convention, and whether it is gauge stage relative to a local zero, an elevation, depth, or another value.
15. Please explain negative and extreme values, including the examples below. Are these valid values, sentinel/error codes, unvalidated measurements, or corrected/revised observations? Please provide relevant validation rules and the data dictionary; we are not asserting that these observations are erroneous.
16. What are the units and precise definitions of `RL_of_zeroGauge` and `MeanSeaLevel`? Are these gauge zero elevations, reference/benchmark elevations, offsets, or other quantities?
17. What vertical datum/reference elevation, benchmark, survey epoch, validity period, and transformation equation apply to each field and water-level value? Can observations and reference values be compared between stations?
18. Some records contain zero values in one or both reference fields. Are those valid zeroes, missing-value placeholders, defaults, or another convention?

### 5. Quality control, revisions, and discharge availability

19. Is an observation-level QC/measurement-status field available? If not, please confirm that no quality flag is supplied in these exports. Provide QC categories, validation methods, suspect/rejected status meanings, and documented sentinel values.
20. What is the authoritative rule for repeated station/timestamp rows? Are they revisions, retransmissions, parallel readings, or duplicates? How are corrections/version history represented and linked to source rows/revision identifiers, and which row should be retained, if any?
21. What does `Is_DischargeDataAvailable` mean, and at what scope/time is it defined? Is it unrelated to the validity of the water-level observation?

### 6. Attribution, license, and permitted use

22. What specific license instrument and version govern each resource? If no standard license applies, could you provide written permission and required attribution?
23. Does the permission cover local retention, research/academic analysis, format conversion and other derivatives, publication of aggregate results, publication of station-level observations, and redistribution of raw or normalized data?
24. Are there commercial-use restrictions, access conditions, attribution wording, embargoes, or requirements to seek additional approval?

### Examples for locating records

These are source-row references from our local CSV copies (line 1 is the header). They are provided only to identify records for explanation; we do **not** claim they are erroneous or choose one value as authoritative.

| File | CSV line / `SlNo` | Station / timestamp | Values as stored |
|---|---|---|---|
| Godavari | 126530 / 126529 and 126531 / 126530 | Bhatpalli, 03-03-2021 17:30 | 185.015 and 166.848 |
| Godavari | 130684 / 130683 and 130685 / 130684 | Bhatpalli, 30-09-2021 08:00 | 194.15 and 184.073 |
| Krishna | 20336 / 20335 and 20337 / 20336 | Bawapuram, 09-10-2021 11:00 | 271.339 and 271.338 |
| Krishna | 138331 / 138330 and 138332 / 138331 | Madhira, 24-10-2021 18:00 | 44.503 and 44.504 |
| Godavari | 942909 / 942908 | Sriram Sagar Reservoir, 28-07-2024 08:00 | -673.0 |
| Godavari | 883229 / 883228 | Sangam (Murredu), 31-07-2022 17:00 | 2583.0 |
| Krishna | 318148 / 318147 | Prakasam Barrage, 28-06-2022 20:00 | -990.33 |
| Krishna | 49767 / 49766 | Bhadra Reservoir, 29-12-2022 02:30 | 1602.237 |

We would also appreciate confirmation of the large station-level gaps identified in the exports, including Kosagumda (Bhaskel), Godavari, 2021-07-20 04:00 to 2024-07-22 23:00, and Shimoga, Krishna, 2021-11-03 08:00 to 2023-12-18 06:00. These gaps are observations about the local files, not a conclusion that a station was inactive or that no measurements exist.

This request is for data-quality, provenance, and permitted-use clarification. It is not a request for operational flood forecasts or an endorsement of the data for hydraulic modelling. We will not normalize the files until the required station mapping, timestamp, measurement/datum, QC and duplicate rules, provenance, and reuse conditions are supported by authoritative evidence.

Thank you for your assistance.

Sincerely,  
`[Name]`  
`[Institution / Department]`  
`[Project supervisor / contact details]`  
`[Date]`
