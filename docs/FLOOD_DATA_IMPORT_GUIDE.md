# Flood training-data source audit and import guide

## Result as of 2026-10-27

**No new source data file was added to the repository. Prediction and training remain `NOT_READY`.** Official portals and metadata were checked; access to a public metadata API is not the same as a complete, licensed, quality-controlled training dataset.

### Official/authorized source findings

| Requirement | Source and verification | What it provides | Remaining issue |
|---|---|---|---|
| CWC gauge water level | [NWDP CKAN CWC water-level package](https://nwdp.nwic.gov.in/api/3/action/package_show?id=68600163-c5a0-4327-aa1a-fa7157b86cce), resource [metadata](https://nwdp.nwic.gov.in/api/3/action/resource_show?id=d80798b9-4b11-4626-8b63-964202ba7216), and [datastore API](https://nwdp.nwic.gov.in/api/3/action/datastore_search?resource_id=d80798b9-4b11-4626-8b63-964202ba7216&limit=1&sort=_id%20desc) | CWC is the publisher; package metadata declares public access, hourly frequency, CSV/API, and metres. The live resource included `Data Acquisition Time`, station name, state/district codes, coordinates, `RL_of_zeroGauge`, `MeanSeaLevel`, and measured water level. | Live resource is named 2026–2030 and is telemetry, not a validated historical series. No stable station ID or quality flag was present in the inspected row. The stage vertical datum and historical completeness need CWC confirmation. |
| Historical CWC readings | NWDP package above lists CWC Subernarekha resources described as 1961–1990 and 1991–2020. The 1961–1990 resource metadata [was checked](https://nwdp.nwic.gov.in/api/3/action/resource_show?id=7b11c75a-a714-461d-b13e-81cbd50df6b7); its CSV response was inspected without saving it into the repository. | The 1961–1990 CSV metadata reports 3,627 bytes and “Other (Open)”/public access. The inspected response contained sparse records, with displayed timestamps from 1969–1975, not a continuous hourly series. | NWDP lists data-quality and validation-method fields as unspecified (`-`). “Other (Open)” is not a specific license. This resource is not sufficient evidence for complete windows or operational training. The 1991–2020 resource is listed at about 30 MB; it was not downloaded because license/quality checks are unresolved and no project data was requested for committing. |
| Danger levels/effective dates | The official [CWC Flood Forecasting portal](https://ffs.india-water.gov.in/) was confirmed to be a CWC portal. NWDP CKAN API searches for an exact “danger level” dataset did not return a dedicated register. | Portal/source for follow-up with CWC and regional offices. | No authorized historical per-gauge danger-level register or effective dates were verified. Do not treat `RL_of_zeroGauge`, `MeanSeaLevel`, or an observed stage as a danger threshold. Ask CWC for gauge ID, threshold values, validity intervals, units/datum, revision history, and reuse permission. |
| Historical weather | [Open-Meteo Historical Weather API documentation](https://open-meteo.com/en/docs/historical-weather-api), [license](https://open-meteo.com/en/licence), and [terms](https://open-meteo.com/en/terms) | Historical gridded weather values. API data is offered under CC BY 4.0 with attribution. Free API terms are for non-commercial use and limits apply; paid plans cover commercial use. | The project's existing request uses `best_match`; the response does not identify one fixed underlying model/resolution. Use gauge-aligned coordinates and record model, returned coordinates, variables, units, API terms/version, and attribution. Do not describe reanalysis as gauge observation. No archive was acquired for this task. |
| Alternative weather archive | [Copernicus Climate Data Store ERA5-Land](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land?tab=overview) | Official global land reanalysis, hourly from 1950, distributed on a 0.1-degree grid (native resolution about 9 km). | These are model-based reanalysis estimates with uncertainty, not direct station data. CDS account/access, dataset-specific license, attribution, and requested product terms must be checked before use. No data was downloaded. |

NWDP's CWC package metadata reports author/maintainer CWC, `Data Access Control: Public`, `isopen: true`, and license title `Other (Open)`; it does not identify a standard license. The live CKAN metadata is mutable, so archive a copy of the exact source metadata and resource IDs with any authorized intake. Source contact shown in that metadata: `rdcdte-cwc@nic.in`; ask for formal confirmation of historical-data availability, the applicable data-sharing/reuse terms, gauge identifiers, vertical datum, quality flags, coverage documentation, and the danger-level register. This contact detail is not evidence that permission has been granted.

## Scientific mapping decision

The existing pipeline creates a provider-resolved weather point for one requested coordinate and retains its returned grid coordinates. That point is **not** a gauge observation or an established hydrologic catchment predictor. Nearest-coordinate matching alone is insufficient: distance does not establish that the weather cell represents the gauge's upstream catchment, that it covers the basin's precipitation, or that its timing aligns with river travel time. Topography, catchment boundaries, channel connectivity, upstream/downstream location, local rainfall gradients, and gauge-to-gauge dependencies remain unverified.

The importer therefore requires an explicit reviewed crosswalk with gauge/grid IDs and coordinates, reviewer/reference, method, and an explicitly approved maximum distance. It reports Haversine distance and checks the declared limit, but does not select nearest points or decide scientific validity. A hydrologist must approve the method, relevant catchment support, and prediction lead-time before a crosswalk may be used. The existing single-location Kochi historical-weather candidate is not representative multi-gauge coverage and must not be used as a substitute.

## Canonical files for manual import

Run commands from the repository root. Keep downloaded provider files unchanged under `ml/datasets/raw_sources/`, grouped by provider and resource; keep canonical inputs under the readiness paths below. Do not put illustrative templates in any of these directories.

```text
ml/datasets/raw_sources/nwdp/cwc_export.csv
ml/datasets/raw_sources/nwdp/resource_metadata.json
ml/datasets/raw_sources/open_meteo/archive.json
ml/datasets/raw_sources/open_meteo/archive.manifest.json
ml/datasets/hydrological/raw/gauge_water_level_observations.csv
ml/datasets/hydrological/raw/official_gauge_danger_levels.csv
ml/datasets/flood_training/gauge_grid_crosswalk.csv
ml/datasets/flood_training/gauge_coverage_evidence.csv
ml/datasets/flood_training/prepared_predictors.csv
ml/datasets/flood_training/source_metadata.json
ml/datasets/flood_training/licensing_evidence.json
```

Keep the provider export and metadata unchanged. Record the URL/resource ID, retrieval time, source checksum, applicable license or written permission, access review, field mapping, and timezone. Hashes and operator-provided review fields provide traceability, not source authentication or permission.

### NWDP/CWC source-format conversion

The inspected NWDP CSV export fields are `Station`, `State LGD Code`, `District LGD Code`, `Latitude`, `Longitude`, `Data Acquisition Time`, and `River Water Level Telemetry Hourly (meter)`; exports may have `_id` and/or `SlNo`. `normalize_nwdp_observations` accepts those provider headers, maps sites only by an exact station/LGD-code/coordinate match, converts the explicitly supplied local source timezone to UTC, and preserves the raw file and SHA-256 in a sidecar manifest. It will not nearest-match a station or infer a gauge ID, datum, or quality flag.

Create `ml/datasets/flood_training/nwdp_site_mapping.csv` from an authoritative gauge registry and independently reviewed field mappings. Required columns are `Station,State LGD Code,District LGD Code,Latitude,Longitude,gauge_id,vertical_datum,quality_flag,mapping_status,mapping_reference,quality_mapping_reference`. The mapping must use a stable authority-issued gauge ID and cite the source for each datum and quality decision. If datum or quality is unknown, enter `UNVERIFIED`; that row may be normalized for inspection but cannot support a target assessment. The literal `APPROVED` mapping status records a human declaration only; it is not checked against the reviewer or source.

```powershell
python -m ml.preprocessing.normalize_nwdp_observations `
  --source ml/datasets/raw_sources/nwdp/cwc_export.csv `
  --site-mapping ml/datasets/flood_training/nwdp_site_mapping.csv `
  --output ml/datasets/hydrological/raw/gauge_water_level_observations.csv `
  --source-timezone Asia/Kolkata
```

Use `Asia/Kolkata` only after confirming that the particular export's naive `Data Acquisition Time` is India Standard Time. For timestamped exports, use the actual declared IANA zone; do not assume the host machine's local zone. The conversion creates `gauge_water_level_observations.manifest.json` beside the canonical CSV, including hashes for both the unchanged source file and mapping. Source `SlNo` is used as the row ID only when `_id` is absent; retain the raw export because a row number may not be globally unique.

An adapter error such as “does not match an explicitly reviewed mapping” requires resolving identity using the official registry; do not widen coordinate tolerance or choose the nearest gauge. A missing `_id` and `SlNo` means there is no preserved source-row identifier. Malformed timestamps, coordinates, or water levels are rejected rather than repaired.

### Weather archive conversion and rerun commands

The acquisition command defaults to the existing Kochi coordinates (9.9312, 76.2673), the existing 2020-01-01 through 2024-12-31 date range, and UTC. Its default raw archive and sidecar manifest are exactly the paths checked by `flood_target_readiness.py`: `ml/datasets/raw_sources/open_meteo/archive.json` and `archive.manifest.json`.

```powershell
python -m ml.preprocessing.acquire_open_meteo_archive
```

No archive is acquired by running the test suite. Before making a real request, review provider terms and avoid overwriting existing files. The command refuses to overwrite either the archive or its manifest unless `--force` is explicitly supplied.

For a non-default location, provide both WGS 84 coordinates and an explicit output path. Use only coordinates from an authoritative gauge record after confirming the gauge identity; this does not establish that the weather grid is hydrologically representative. To put the selected archive at the readiness path, use:

```powershell
python -m ml.preprocessing.acquire_open_meteo_archive `
  --latitude <reviewed_gauge_latitude> `
  --longitude <reviewed_gauge_longitude> `
  --start-date 2020-01-01 `
  --end-date 2024-12-31 `
  --output ml/datasets/raw_sources/open_meteo/archive.json
```

Do not use `--force` unless replacing that exact archive and its manifest is explicitly intended and authorized. The readiness service currently checks one canonical archive path; separately named per-gauge archives are not automatically discovered as multi-gauge coverage.

The manifest distinguishes requested coordinates from provider-returned grid coordinates and records the requested date range, returned dates, UTC settings, units, row count, retrieval time, and source-file hash. The request asks for `best_match`; the manifest reports the model and spatial resolution as unavailable unless the response itself supplies those fields. It records licensing evidence as `NOT_VERIFIED`; a generated manifest or a catalog URL is not permission.

The feature builder accepts the Open-Meteo Archive JSON response (not CSV), reads its sidecar manifest, checks required daily variables, and writes the six contract features plus a data-quality/provenance manifest. It uses the same canonical archive path by default; an explicit `--input` supports a separately reviewed archive without copying it into another competing default location. One archive is not multi-gauge coverage. Do not label unrelated coordinates as a gauge match or combine grids without an explicit, reviewed procedure.

```powershell
python -m ml.preprocessing.flood_environmental_dataset `
  --input ml/datasets/raw_sources/open_meteo/archive.json `
  --output ml/datasets/flood_training/prepared_predictors.csv
```

The `--input` must have a matching `<archive>.manifest.json` created with the source archive, not a hand-written or illustrative manifest. Review requested and returned coordinates, date range, units, and terms. Provider model identity and native resolution may be unavailable; do not infer them from the `best_match` request.

Once every canonical evidence file and the five source entries in `source_metadata.json` have been reviewed, assess candidate windows (this does not create labels):

```powershell
python -m ml.preprocessing.flood_training_data_import `
  --observations ml/datasets/hydrological/raw/gauge_water_level_observations.csv `
  --danger-levels ml/datasets/hydrological/raw/official_gauge_danger_levels.csv `
  --crosswalk ml/datasets/flood_training/gauge_grid_crosswalk.csv `
  --coverage ml/datasets/flood_training/gauge_coverage_evidence.csv `
  --predictors ml/datasets/flood_training/prepared_predictors.csv `
  --source-metadata ml/datasets/flood_training/source_metadata.json `
  --output ml/datasets/flood_training/window_assessments.csv `
  --observation-timezone Asia/Kolkata
```

The metadata entry for each source (`observations`, `danger_levels`, `crosswalk`, `coverage`, `predictors`) must include `source_name,source_url,access_status,license_status,license_reference,license_evidence_reference,retrieved_at_utc,source_timezone,raw_source_file,raw_source_sha256,field_mapping_reference`. For normalized NWDP observations, reference the unchanged raw export and its actual hash; for predictors, reference the original weather JSON and its manifest, not just the derived CSV. Store the applicable source-specific documentary license evidence in `ml/datasets/flood_training/licensing_evidence.json`; an Open-Meteo URL or NWDP “Other (Open)” catalog string is not proof that the intended reuse is permitted.
For `observations`, also declare `water_level_unit` (must be `m`) in `source_metadata.json`. Keep the gauge-specific `vertical_datum` in the reviewed mapping and normalized observations, with the same datum recorded in official danger-level rows. These declarations are consistency checks, not provider authentication.

Rerun the report after imports or evidence review:

```powershell
python -m ml.preprocessing.flood_target_readiness `
  --root . `
  --output ml/datasets/flood_training/readiness_report.json
```

The readiness report lists each gate separately: official danger levels, vertical-datum agreement, complete monitoring coverage, negative-window verification, gauge/grid scientific review, historical weather coverage, licensing, target approval, and evaluated model. Its `syntax_status` describes parsing only; `source_verification_status` and `scientific_review_status` remain distinct. A CSV/JSON can be present or parse successfully while its source evidence remains unverified. `DECLARED_APPROVED_UNVERIFIED`, `DECLARED_COMPLETE_UNVERIFIED`, and `CANDIDATE_CHECKS_ONLY` do not satisfy the gate. The service and API remain `NOT_READY`; the report never promotes status.

The sample files in `ml/preprocessing/templates/` demonstrate headers only. Every row is expressly illustrative and carries `ILLUSTRATIVE_ONLY`/`UNVERIFIED` sentinels. Do not copy the sample rows, put them in the import paths, create metadata declaring them genuine, or use them for training.

1. `gauge_water_level_observations.csv`
   - Required: `gauge_id,source_record_id,observed_at,water_level_m,vertical_datum,quality_flag`
   - `gauge_id` must be a stable provider-approved ID, not a generated coordinate hash or station name alone. `source_record_id` must identify the original row.
   - `observed_at` must be ISO-8601 with offset/`Z`, or source format `DD-MM-YYYY HH:MM` accompanied by the documented IANA source timezone. NWDP's inspected `Data Acquisition Time` is local-style; current collector configuration interprets it as `Asia/Kolkata`, but confirm this with the source for every imported product.
   - Map source-specific quality flags only from an authoritative data dictionary. The canonical importer accepts `VALID`, `GOOD`, and `APPROVED`; unknown/suspect/missing levels are not valid samples. NWDP's inspected water-level row had no quality flag, so do not mark it `VALID` without a documented QC basis.
   - Vertical datum must identify the actual gauge datum. Stage and danger threshold must use the same verified datum and units. Do not assume `RL_of_zeroGauge` or `MeanSeaLevel` defines the measurement datum.
2. `official_gauge_danger_levels.csv`
   - Required: `gauge_id,threshold_record_id,effective_from,effective_to,danger_level_m,vertical_datum,unit`
   - Use ISO-8601 timezone-aware instants. Intervals are half-open `[effective_from,effective_to)`; they must not overlap and one verified interval must cover the entire prediction window.
   - `unit` must be `m`. Preserve official identifiers, revision/effective dates, datum, source document URL, and source row ID.
3. `gauge_grid_crosswalk.csv`
   - Required: `gauge_id,grid_location_id,gauge_latitude,gauge_longitude,grid_latitude,grid_longitude,approved_max_distance_km,review_status,reviewer,reviewed_at_utc,reference,matching_method`
   - WGS 84 decimal degrees; `review_status` must be `APPROVED`; the approved distance limit must come from the actual review, not a generic default.
4. `gauge_coverage_evidence.csv`
   - Required: `gauge_id,window_start_utc,window_end_utc,expected_interval_minutes,complete_status,evidence_reference,source_record_id`
   - Use timezone-aware ISO-8601 instants; only explicit `CONFIRMED_COMPLETE` coverage may support a negative. Attach source/operator QC evidence establishing the interval and observation cadence. Row counts alone do not prove that the provider had no omitted readings.
5. Candidate predictors
   - Use rows produced from authorized historical weather data by the existing `ml.preprocessing.flood_environmental_dataset` feature builder.
   - Required columns: `location_id,grid_latitude,grid_longitude,prediction_issue_time_utc,candidate_target_window_start_utc,candidate_target_window_end_utc`, followed by the six ordered features in `ml/preprocessing/feature_contract.json`.
   - Issue and window times must be timezone-aware; window must exactly equal `[issue_time_utc, issue_time_utc + 24 hours)`. All six features must be present and finite.
6. `source_metadata.json`
   - Must contain a `sources` object with one entry for `observations`, `danger_levels`, `crosswalk`, `coverage`, and `predictors`.
   - Each entry requires `source_name,source_url,access_status,license_status,license_reference,license_evidence_reference,retrieved_at_utc,source_timezone,raw_source_file,raw_source_sha256,field_mapping_reference`. The raw source file must be retained or identified by an absolute path, and the declared SHA-256 is checked. These fields are user-supplied provenance only; they do not prove source authority, license rights, quality, or review.
7. `licensing_evidence.json`
   - Must contain a `sources` object with entries for `observations`, `danger_levels`, `crosswalk`, `coverage`, and `predictors`.
   - Every entry must declare `license_name,evidence_reference,applicable_uses,redistribution_terms,reviewer,reviewed_at_utc`. Keep the actual license text or written permission record, version/URL and any restrictions in the evidence repository identified by `evidence_reference`. These fields are inventory, not proof: a qualified reviewer must verify the record applies to the actual data and intended model use.

Omit `--observation-timezone` only when every observation timestamp itself carries an explicit timezone. The timezone flag applies only to naive observation timestamps; threshold, coverage, review, retrieval, and predictor times must carry a timezone.

The exact commands above use actual project paths from the repository root. Never modify a provider's raw export in place. The validator writes a *window assessment* CSV and a manifest of input/output SHA-256 hashes; it does not emit a training-ready label dataset.

### Gauge-package preflight

Before attempting window assessment, check the prospective source package without creating labels:

```powershell
python -m ml.preprocessing.flood_gauge_package_preflight `
  --root . `
  --output ml/datasets/flood_training/gauge_package_preflight.json
```

The report checks the official-site mapping, canonical gauge observations, danger-level intervals, coverage declarations and gaps, weather crosswalk/grid alignment, source/normalization provenance, timestamps/timezones, and the five-source permission inventory. It lists missing files, invalid fields, and evidence still needed. It also checks the unchanged NWDP export at `ml/datasets/raw_sources/nwdp/cwc_export.csv` and provider metadata at `resource_metadata.json`; the observation normalizer manifest must hash-link those raw inputs, the canonical site mapping, and output. For documented gaps, add `gap_start_utc,gap_end_utc,gap_reason` columns to the coverage CSV; a declared gap remains `UNVERIFIED` for completeness and cannot support a negative window.

Each requirement uses one of four states:

- `MISSING`: a required file or declaration is absent.
- `INVALID`: syntax, field values, hashes, timestamps, units, coordinates, or consistency checks failed.
- `UNVERIFIED`: values are illustrative/test-only, unknown, declare a gap, or await external source/scientific verification.
- `READY`: local package syntax and declared fields pass only. `source_verification_status` remains `NOT_VERIFIED` and `scientific_review_status` remains `NOT_REVIEWED`; this is not approval.

The report's `training_readiness` is always `NOT_READY`. It is also included as `gauge_package_preflight` in the normal flood-target readiness report and backend `/api/data-readiness` response. A syntactically complete package can be ready for external review without being official evidence. The checks cannot authenticate a gauge registry, source export, license/permission record, monitoring completeness claim, or catchment assessment. Template rows and `TEST_ONLY` examples never count as evidence.

### Canonical field meanings

| File/field | Meaning |
|---|---|
| Observation `gauge_id` | Stable, authority-issued gauge identifier; not a station-name or coordinate-derived ID. |
| `source_record_id` | Provider row/record identifier preserved from the raw export (`_id`, or `SlNo` only if no `_id` is supplied). |
| `observed_at` | Instant of the stage reading, normalized to UTC; any conversion from local time must use the source's confirmed timezone. |
| `water_level_m` | Observed river stage in metres, not rainfall, elevation, or a danger threshold; blank/suspect rows cannot support a negative. |
| `vertical_datum` | Explicit vertical reference for the reported stage; it must match the effective official danger-level datum. |
| `quality_flag` | Source-defined QC result mapped using an authoritative data dictionary; only the importer-supported valid flags count as valid readings. |
| Danger `threshold_record_id` | Official source ID/version for this gauge's danger-level record. |
| `effective_from`, `effective_to` | Timezone-aware instants delimiting the threshold's half-open validity period `[from,to)`; one period must cover the whole forecast window. |
| `danger_level_m`, `unit`, `vertical_datum` | Official threshold value and its unit/reference; importer currently requires metres and matching stage datum. |
| Crosswalk `grid_location_id` | Stable key of the returned weather grid point; must equal the predictor row's `location_id`. |
| `gauge_latitude`, `gauge_longitude` | Gauge coordinates from an authoritative station registry, WGS 84 decimal degrees. |
| `grid_latitude`, `grid_longitude` | Provider-returned weather grid coordinates, WGS 84 decimal degrees; not necessarily the requested point. |
| `approved_max_distance_km` | Distance bound explicitly justified by the scientific review, not a convenience tolerance. |
| `review_status`, `reviewer`, `reviewed_at_utc`, `reference`, `matching_method` | Declared human review state, reviewer identity, review instant, evidence reference, and method used. These are not independently authenticated and do not alone prove catchment suitability. |
| Coverage `window_start_utc`, `window_end_utc` | Start/end of the interval for which source monitoring completeness is claimed. |
| `expected_interval_minutes` | Provider sampling cadence used to compute the expected timestamps in that interval. |
| `complete_status`, `evidence_reference`, `source_record_id` | Declared coverage/QC result and the provider record/log supporting it; row counts are not coverage evidence. |
| Predictor `prediction_issue_time_utc` | Time at which inputs would have been available for a forecast. |
| `candidate_target_window_start_utc`, `candidate_target_window_end_utc` | Exact half-open 24-hour UTC outcome window; start must equal issue time. |
| Predictor `location_id`, `grid_latitude`, `grid_longitude` | Grid identity and provider-returned coordinates; they must match the reviewed crosswalk. |
| Six weather features | Antecedent 1/3/7-day precipitation sums (mm), daily mean temperature (°C), daily mean relative humidity (%), and daily maximum wind speed (km/h). Their exact source variables and transformations are in `ml/preprocessing/feature_contract.json`. |
| Provenance `source_name`, `source_url` | Provider/product name and exact source/resource location. |
| `access_status`, `license_status`, `license_reference`, `license_evidence_reference` | Operator declarations and location of supporting terms/permission evidence; they do not prove lawful access or reuse. |
| `retrieved_at_utc`, `source_timezone` | Retrieval instant in UTC and the confirmed source timezone for naive times. |
| `raw_source_file`, `raw_source_sha256` | Retained unchanged source file path and exact-byte SHA-256 checked by the importer. |
| `field_mapping_reference` | Versioned mapping/transform record linking source headers to canonical fields. |

### Interpreting validation outcomes

- Missing/unexpected CSV columns mean the source schema is different from the reviewed mapping. Preserve the export and add an explicit, reviewed field mapping; do not rename a field based on a guess.
- An unknown/ambiguous timezone or invalid timestamp stops normalization. Confirm the source's timezone and timestamp semantics with the provider; never use the computer's local timezone as a substitute.
- A duplicate gauge/time observation is rejected. Compare provider record IDs and source revisions; only resolve a true duplicate using source evidence, and retain every raw row.
- Unknown datum, unknown QC, missing water level, or a non-valid quality flag cannot support a negative. Obtain gauge datum and QC documentation; do not replace unknown values with sea level, zero, or `VALID`.
- Threshold unit, effective-date, interval overlap, or datum errors require a corrected official threshold record. Never infer a threshold from a measured stage, gauge-zero field, or current warning.
- Missing/incomplete coverage, a missing sample, a mismatch between expected cadence and observed timestamps, or an unverified coverage declaration results in `INDETERMINATE_INCOMPLETE_COVERAGE`, not a negative label.
- An unapproved/missing crosswalk, mismatched grid coordinates, or a distance-limit failure requires a gauge/catchment review. Do not select a nearest cell or raise the distance tolerance just to pass.
- A source hash mismatch means the file differs from the version recorded in provenance. Preserve the original and update provenance only after confirming the replacement source/version and its license.
- A predictor issue/window mismatch or missing/non-finite feature requires rebuilding from the correct archive and checking its dates, variables, coordinates, UTC basis, and source manifest.
- Missing license evidence, a bare catalog URL, or a `DECLARED_*_UNVERIFIED` status is an external review blocker, not a syntax problem. Obtain the actual applicable license/permission record and document allowed use.

These are diagnostic instructions, not automatic approvals. Do not edit values solely to make validation pass.

Assessment values (checks apply to declared evidence; they do not independently authenticate the provider, reviewer, license, or scientific approval):

- `POSITIVE_EVIDENCE_CHECKS_PASSED`: at least one valid, datum-compatible observation reaches the declared danger level, for an exactly matched reviewed crosswalk/window.
- `NEGATIVE_EVIDENCE_CHECKS_PASSED`: one declared complete-coverage record covers the whole window, its cadence produces an exact expected timestamp set, every expected observation is present and valid, all levels are below the declared threshold, the threshold is effective for the full window, and the reviewed crosswalk/grid coordinates match.
- `INDETERMINATE_*`: any other condition, including missing threshold, incomplete coverage, invalid/missing measurement, unreviewed/mismatched gauge-grid mapping, or unknown datum. It does not get a training label and must not be converted to zero.

The output is an evidence assessment, not an approved label file; it deliberately contains no `flood_occurrence` training target because the target remains proposed and unapproved. Domain approval, source/license review, multi-site representativeness, leakage-resistant model evaluation, and inference implementation are separate gates; the API does not become ready when files appear.
