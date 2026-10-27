# Physics-Based Flood Modelling Preparation

## Status and scope

This is **Stage 2 Part A preparation only**. No hydraulic solver has been selected, installed, configured, or run. Flood prediction and inference remain `NOT_READY`; no new alert path or model endpoint is enabled. The existing React/Vite Digital Twin remains an illustrative scenario demonstrator, not a hydraulic model.

The existing [`readiness_report.json`](../ml/datasets/flood_training/readiness_report.json) was inspected read-only and remains `NOT_READY` with target `cwc_gauge_danger_level_exceedance_24h_v1` still `PROPOSED_REQUIRES_DOMAIN_APPROVAL`. The gauge package preflight and flood-target readiness scripts remain separate and unchanged. Their checks must not be inferred from this new configuration preflight.

## Repository audit

| Existing component | Finding | Stage 2 Part A treatment |
|---|---|---|
| React/Vite `/simulation` page and `scenarioEngine.js` | 25 deterministic illustrative frames; does not calculate depth, extent, arrival time, or probability | Preserved; no solver calls or new model results in the UI |
| FastAPI `/api/simulations` | Existing authenticated weather-based what-if route and persisted scenario estimates | Preserved; not repurposed as a hydraulic execution endpoint |
| GIS API and map | Existing six GeoJSON overlays are display layers, off by default; GIS readiness checks files, coordinate structure, CRS and Kochi overlap | Preserved; these checks do not establish engineering survey quality or solver suitability |
| Existing GIS assets | SRTMGL1 DEM and OSM/HydroSHEDS-derived reference geography are documented in the data acquisition report | Treated as reference assets only; no new suitability or licensing claim |
| Hydrology collectors and schemas | Provider telemetry and collection/freshness state exist, with freshness based on observation times | No collector changes; a station/resource being present does not establish Kochi catchment relevance |
| Gauge package and target readiness | Existing tooling checks gauge package declarations, observations, danger levels, coverage, provenance and target blockers | Not duplicated or changed; continue to use existing reports for those workflows |
| Historical flood/event data | EM-DAT supplies event history, not a validated continuous hydraulic calibration target | Not used as channel geometry, gauge observations, or model labels |

No verified channel survey/cross-sections, structures inventory, Kochi-linked gauge package, approved danger-level register, model boundary series, or event-separated calibration and validation package was established by this audit. GIS reference file presence is not evidence that these inputs exist.

## Modelling approach assessment

### HEC-RAS candidacy

USACE describes HEC-RAS as supporting one-dimensional steady-flow and one- and two-dimensional unsteady-flow computations, in addition to sediment/mobile-bed, stormwater-pipe, temperature and water-quality capabilities. This makes it a plausible candidate for channel hydraulics and floodplain-flow analysis, subject to the study question and verified inputs. See the [official HEC-RAS overview](https://www.hec.usace.army.mil/software/hec-ras/) and [HEC-RAS User's Manual](https://www.hec.usace.army.mil/confluence/rasdocs/rasum/latest).

- **1D** is a candidate for a defined river reach where the main question is longitudinal channel stage/flow and defensible surveyed cross-sections, reach connectivity, structures, and boundary conditions are available. It is not automatically adequate for complex lateral floodplain flow.
- **2D** is a candidate where spatial floodplain pathways, lateral spreading, or urban flow interactions are central. It requires suitable terrain and a defensible representation of channels, obstructions, hydraulic structures, roughness, boundaries, and wetting/drying behaviour; a solver run alone does not establish accuracy.
- **Coupled 1D/2D** may be appropriate for a channel reach interacting with a floodplain, but coupling setup and numerical stability require specialist review.
- **Rainfall-runoff is a separate modelling question.** A hydraulic river model requires inflows and downstream conditions. Catchment rainfall-to-runoff generation may need a hydrologic model or a separately justified, observed flow boundary series. Urban drainage/flooding may additionally require a drainage-network model. These components must not be approximated by the Stage 1 rainfall animation.

The available Kochi DEM is a roughly one-arc-second SRTM reference raster, in geographic coordinates, documented with elevations from -34 to 106 m. Its vertical datum, channel bathymetry, local accuracy, vegetation/building representation, and suitability for hydraulic mesh/cross-sections are not established here. Existing OSM rivers and HydroSHEDS basin polygons are reference geography, not surveyed channel geometry. Therefore no 1D/2D choice, terrain adequacy, or catchment/gauge match is confirmed for this study area.

### Alternatives and recommendation

Keep the solver behind a file-based adapter contract. HEC-RAS is a **candidate, not a project selection**. Compare it with a suitable hydrologic rainfall-runoff component (for example HEC-HMS) if observed inflow generation is needed, and with an urban drainage model (for example EPA SWMM) if drainage-network behaviour is in scope. A different hydraulic solver can later implement the same adapter contract. Selection requires a defined research question, study domain, data inventory, qualified review, software/platform assessment, and an evaluation plan.

The HEC public pages confirm the model family and capabilities cited above. This audit did not verify a specific release's Windows requirements, automation/API guarantees, hardware sizing, redistribution terms, or compatibility with this deployment. Verify those items from the chosen release's official download, release notes, and license before any installation or automation. Do not install a solver merely to run the current application.

## Proposed integration architecture

1. **React/Vite frontend:** keep Stage 1 labelled illustrative. A future results view may display only a run artifact whose validation state and provenance are explicit; it must not treat a successful HTTP response as a forecast.
2. **FastAPI backend:** continue to serve existing routes. A future authenticated run/status API is a separate change gated on readiness and review. It is not part of this preparation.
3. **Input acquisition/validation:** import immutable source files into a controlled run package; record source identifiers, licenses/evidence, retrieval time, units, CRS, datums, quality flags, hashes, and coverage. Validate before any solver process is created.
4. **Solver-neutral adapter:** define an interface such as `validate_inputs`, `prepare_run`, `execute`, and `collect_outputs`. Keep solver-specific project creation, process invocation, and output parsing outside React, the current scenario engine, and route handlers.
5. **Configuration and run metadata:** store a versioned config, source hashes, code/adapter/solver versions, time window, CRS/datums, settings, approval states, and reproducibility information for each future run.
6. **Execution and results:** execute in an isolated worker with bounded resources/timeouts. Write to a run-scoped directory outside static web roots; preserve solver logs, input manifest, and raw outputs. Never overwrite source data.
7. **Map conversion:** only after independent output validation, convert supported results to a declared map format (for example GeoJSON for bounded vector features or Cloud Optimized GeoTIFF for raster surfaces) with CRS, units, time slice, nodata, and resolution. A format conversion is not scientific validation.
8. **Provenance and uncertainty:** attach run ID, source/config hashes, solver version, assumptions, domain, timestamps, calibration/validation status, limitations, and uncertainty/sensitivity results to every result.
9. **Failure and reproducibility:** distinguish rejected input, validation error, solver failure/timeout, output parse/QA failure, and completed-but-unvalidated runs. Keep structured, credential-free logs and make reruns reproducible from immutable inputs/configuration.
10. **Digital Twin boundary:** a future, explicitly approved adapter may supply a separate validated overlay. It must not replace the Stage 1 illustrative engine or enable warnings. Prediction/alert systems require their own gates and domain approval.

## Input-data contract

Each package must include an immutable manifest with file hash, source ID/name/URL, retrieval time, field mapping, license evidence, and separate review states. `READY` for a technical check means only that the declared syntax/metadata passed that check; it does not mean source authenticity, legal permission, scientific fitness, or model readiness.

| Input | Minimum metadata and deterministic checks |
|---|---|
| Terrain/elevation | Readable raster; horizontal CRS and coordinate units; horizontal resolution; elevation units and vertical datum; coverage; nodata/void handling; source/hash/license; accuracy and acquisition date. Reproject to an appropriate metric model CRS where necessary. Confirm vertical datum and channel/bathymetry compatibility. |
| Channel geometry | Surveyed coordinates/elevations, bank stations, cross-section/reach IDs, channel dimensions, connectivity, structures (bridges, culverts, gates) where relevant, survey date/accuracy, CRS, horizontal/vertical units/datums, source/license, and coverage. |
| Gauge metadata | Official station ID/name, provider registry reference, coordinates, river/catchment association, measurement type, units, station datum, observation interval, quality-flag mapping, operation period, source/license, and evidence that the site represents the modeled reach/catchment. |
| Water-level/flow observations | Source record identity, UTC-aware timestamps, value, units, datum, quality flag, station ID, duplicate/gap checks, provider corrections, temporal coverage, and explicit conversions to the model datum. Missing observations remain missing. |
| Official danger levels | Official source/authority, gauge ID, value, units, datum, effective-from/to dates, revision provenance, and reuse permission. A threshold is not a hydraulic boundary condition or a model calibration result. |
| Rainfall/meteorology | Observed or appropriately justified forcing source, variable/units, timestamp/timezone, temporal and spatial resolution, coverage, missing-data policy, source/license, and station/grid-to-catchment mapping. Forecast forcing and observed rainfall must be distinguished. |
| Initial conditions | Initial water surface/flow and any required soil/storage state, units/datum, timestamp, method, supporting observations, and justification. |
| Upstream/downstream conditions | Boundary type and values/series, units, datum, timestamps, locations, source, coverage, and hydrologic justification. They must be compatible with model domain and time step. |
| Calibration and independent validation | Identified events and observed response data, quality/coverage, shared datum/units, separation by event/time (no leakage), provenance, chosen metrics, and reviewer. Validation data must not be reused to tune the model. |

Time-series timestamps must be explicit-offset ISO-8601 and monotonic/unique in the current scaffold. Vertical levels cannot be compared until a common datum or documented, reviewed transformation is established. Spatial overlap with a study-area rectangle is only a coarse consistency check, not proof of catchment membership or adequate coverage.

## Non-operational configuration and preflight

Template: [`ml/configs/hydraulic_model_config.template.json`](../ml/configs/hydraulic_model_config.template.json). It intentionally contains null placeholders and `execution_enabled: false`; it names no gauge, danger level, geometry, boundary value, solver version, or calibration result.

The standard-library preflight is [`hydraulic_model_preflight.py`](../ml/preprocessing/hydraulic_model_preflight.py). It checks required config fields, a projected model CRS declaration, WGS 84 study bounds, time-window order/timezone/time step, project-contained file paths, file hashes, basic GeoJSON/CSV/TIFF structure, required CSV columns, time-series timestamp ordering, declared units/datums, and coarse spatial overlap. Run it from the repository root:

```powershell
python -m ml.preprocessing.hydraulic_model_preflight --config ml/configs/hydraulic_model_config.template.json
```

The template is expected to report missing fields and exit non-zero. The command never executes a solver and `execution_permitted` is always false, even when technical checks pass. File presence or a review-reference string cannot verify source authenticity, licensing, domain approval, or scientific suitability; those axes remain `MISSING`/`UNVERIFIED`. The scaffold does not replace the existing gauge package preflight or flood target readiness checks, and it is not wired to API, prediction, alert, or map readiness.

Each populated input descriptor needs `path`, `format`, `sha256`, `source_name`, `source_id`, `source_url`, `retrieved_at_utc`, `crs`, and `units`. Add `vertical_datum` for terrain, geometry, gauge, water-level, and danger-level inputs. Spatial inputs include WGS 84 `coverage_bounds_wgs84`; raster inputs include resolution; CSV files include `required_columns`; time series identify `timestamp_column` and, when needed, `series_key_columns`; gauge metadata identifies latitude/longitude columns; danger-level tables identify effective interval columns; and calibration/validation tables identify an `event_id_column`. CRS mismatches against the projected model CRS are rejected for terrain, channel geometry, and rainfall grids until reprojected. Gauge latitude/longitude columns remain explicitly WGS 84. Timestamp intervals, station coordinates, and disjoint calibration/validation event IDs are checked deterministically. Raster geospatial metadata values and external evidence are not authenticated by this lightweight preflight.

`technical_status: READY` means only that the local syntax/manifest checks passed. `UNVERIFIED` review states remain separate, and execution/readiness remain `NOT_READY`; the preflight cannot promote either.

## Scientific and safety gates

Before any real run is considered for operational or user-facing use, require documented sign-off for each gate:

1. Source authenticity and reuse/licensing reviewed.
2. Study area, catchment, gauge IDs/coordinates, and hydrologic relevance confirmed.
3. Terrain, channel geometry, structures, units, horizontal CRS, and vertical datums checked.
4. Initial state and upstream/downstream boundaries justified for the event/time window.
5. Model domain, mesh/cross-sections, parameters, and setup reviewed by a qualified person.
6. Calibration performed on suitable observations with documented objective metrics.
7. Independent validation completed on held-out events/data with documented metrics.
8. Sensitivity and uncertainty assessed, including forcing, parameters, and input-data uncertainty.
9. Output resolution, limitations, failure modes, and intended use documented.
10. Automated safeguards prevent unvalidated output from triggering alerts or being shown as a verified forecast.

A solver exit code of zero proves neither calibration quality nor predictive accuracy. No model result from this preparation can trigger an alert.

## Blockers and next actions

**Requires a verified gauge/source response:** official station registry metadata and IDs; confirmation of Kochi catchment/reach membership; quality-controlled observations and datum; official danger thresholds and effective dates; provider field semantics, retrieval evidence, and use/license terms; rainfall observations/forcing coverage; and source response limitations. Current nationwide hydrology records do not establish these relationships.

**Can proceed without the response:** refine the research question and study domain; consult a qualified hydrologist; inventory candidate terrain/geometry sources and their licenses; obtain official software requirements and terms for a solver candidate; design versioned manifests and review checklists; and evaluate adapter boundaries. No new datasets were downloaded or overwritten here.

**Must wait:** solver selection for the catchment, hydraulic geometry/boundary setup, calibration, independent validation, any usable flood-depth/extent product, operational warning integration, or model/inference readiness. Do not fill the gaps with synthetic observations, labels, danger levels, or assumed thresholds.

## Verification record

Focused validation commands and exact outcomes are recorded in [`STAGE_2_PART_A_VERIFICATION_RESULTS.md`](./STAGE_2_PART_A_VERIFICATION_RESULTS.md).
