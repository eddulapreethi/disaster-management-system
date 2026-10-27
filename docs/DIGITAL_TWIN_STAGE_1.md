# Digital Twin Stage 1 Demonstrator

## Status and scope

The Stage 1 Digital Twin is an interactive, software-only scenario demonstrator in the existing authenticated `/simulation` page. It is not a hydraulic model, a flood forecast, or an emergency-warning system.

> **Stage 1 illustrative scenario only — not a validated flood forecast or emergency-warning system.**

The page uses the existing Kochi GIS study area and Leaflet/React-Leaflet map. The available reference GIS files cover Kochi only; selecting a focus point does not establish a gauge location or catchment. Flood prediction remains `NOT_READY`. Stage 1 does not call prediction, alert, recommendation, weather, or simulation APIs and does not save generated scenarios to the backend.

## Architecture

- `frontend/src/pages/Simulation.jsx` owns the page controls, scenario state, playback timer, map and results.
- `frontend/src/digitalTwin/scenarioEngine.js` is the pure deterministic scenario and timeline module. It validates inputs, produces fixed-step frames, compares scenario input totals, bounds focus points to the documented Kochi GIS rectangle, and exposes a timeline reducer.
- `frontend/src/maps/RiskMap.jsx` continues to provide the existing risk markers and independently toggled GIS layers. Optional props add the Stage 1 symbol and allow selecting a focus point within the Kochi bounds; existing Risk Map pages retain their previous defaults.
- `frontend/src/maps/geoJsonLayers.js` and the authenticated `/gis/layers/{layer_name}` route provide the six existing GeoJSON overlays. They remain lazy-loaded, individually toggleable, and off by default. Existing attribution and license cautions remain in the map controls.
- The backend `/simulations` route and Python weather-based estimate remain available for existing API clients, but this page does not call that route or turn its estimate into Stage 1 map output.

The elevation raster was not used. Although the repository contains a Kochi DEM, elevation alone does not provide a hydraulic water-spread algorithm, calibrated boundary conditions, drainage representation, or validation. Stage 1 therefore does not render a flood polygon, affected-area estimate, depth, arrival time, population impact, or risk probability.

## Scenario method and assumptions

Inputs are a user-selected rainfall intensity (0–300 mm/hour), scenario duration (1–72 hours), and an optional user-entered initial river level (0–30 m). The river-level field has no verified gauge default and is recorded as illustrative context only; it does not affect the map marker or rainfall sequence.

The Low, Moderate, and High presets are explicitly illustrative user-input examples:

| Preset | Rainfall input | Duration |
|---|---:|---:|
| Low | 5 mm/hour | 3 hours |
| Moderate | 20 mm/hour | 6 hours |
| High | 50 mm/hour | 12 hours |

These are not observed, forecast, return-period, or locally calibrated rainfall values. A scenario contains 25 deterministic frames. At each frame, the displayed accumulated rainfall input is `entered rate × elapsed scenario hours`; it is not runoff, river stage, flood depth, or inundation. Comparison uses the same elapsed-time fraction of each scenario and reports only the arithmetic difference and relative change in accumulated rainfall input. Relative percentage is unavailable when Scenario A's input total is zero.

The animated map symbol is centered on the selected focus coordinate. Its screen-space size varies with the bounded input intensity and timeline progress. This is only a visual cue; it encodes no physical distance or geographic extent. The focus coordinate initially uses the geometric center of the packaged Kochi study-area bounding box, not a measured gauge. Clicking the map can choose another focus point inside that box.

## How to run and use

From `frontend/`:

```powershell
npm install
npm run dev
```

Sign in and open **Digital Twin** from the sidebar (route `/simulation`). Choose the Kochi study-area or map-selected focus-point mode, toggle any desired reference GIS layers, optionally click inside the map to set the focus point, choose a preset or enter values, and run Scenario A. Use Play, Pause, Reset, the timeline slider, and playback-speed slider to inspect frames. Enter another set of inputs and run Scenario B to compare the two illustrative rainfall-input totals at the same timeline fraction.

Values outside the displayed ranges or non-finite values are rejected. An omitted river level remains absent; the interface never substitutes a measured or default reading. Existing GIS loading, error, and retry states remain available. No non-Kochi study area is offered.

## Limitations

- No hydrology, terrain flow, drainage, infiltration, soil, channel geometry, structures, boundary conditions, or observed gauge series is modeled.
- A map symbol is not a flood boundary or hazard footprint. No geographic area is calculated.
- Rainfall presets and user entries are not provider observations or forecasts.
- The optional river-level entry is not verified and does not affect the animation.
- Reference GIS layers do not establish flood conditions and retain their individual source/attribution and redistribution caveats.
- No scenario result is linked to real alerts or automatic danger labels. Stage 1 cannot make an emergency decision.
- The initial packaged coverage is Kochi only; other regions and catchments are unsupported.

## Stage 2 requirements

A physics-based Stage 2 must be treated as a separate model-development and validation project. At minimum it needs:

1. A reviewed Kochi catchment and model domain, verified gauge coordinates, channel/catchment boundaries, and compatible horizontal/vertical datums.
2. Licensed, quality-controlled terrain and bathymetry/channel geometry, drainage/network and relevant structure data; DEM elevations alone are insufficient.
3. Defensible spatial and temporal rainfall inputs, boundary conditions, initial conditions, soil/infiltration and roughness parameters, with provenance and units.
4. An established hydraulic/hydrologic solver or independently reviewed equations and numerical implementation, including stability and conservation checks.
5. Historical calibration events and independent validation events with observed river levels and, where available, mapped inundation; uncertainty and sensitivity analysis.
6. Expert review of model suitability, operational failure modes, intended use, and any separate approval required before warning integration.
7. Tests for data contracts, numerical invariants, reproducibility, performance, uncertainty, API gating, and confirmation that unvalidated results cannot generate alerts.

Passing UI tests or having map assets is not evidence that these requirements are met. Flood prediction remains `NOT_READY` unless its separate readiness and model-evaluation requirements pass.

## Verification

Focused frontend checks:

```powershell
cd frontend
npm test
npm run build
```

Relevant backend regression checks from the repository root:

```powershell
python -m pytest backend\tests\test_gis_api.py backend\tests\test_simulation_api.py backend\tests\test_simulation_service.py -q
```

Run `git diff --check` from the repository root.

### Results for this Stage 1 implementation

- `npm.cmd test` in `frontend/`: **18 passed, 0 failed**.
- `npm.cmd run build` in `frontend/`: **passed** (Vite production build).
- `python -m pytest backend\tests\test_gis_api.py backend\tests\test_simulation_api.py backend\tests\test_simulation_service.py -q`: **10 passed**. The installed Starlette/httpx test-client combination emits a deprecation warning.
- `git diff --check`: **passed**.
- A local browser smoke check exercised scenario creation, comparison, frame scrubbing, playback, pause, reset, invalid-value feedback, and a 375-pixel viewport without horizontal page overflow. That check used placeholder browser authentication while the backend was offline; it does not verify authenticated GIS layer loading or real account behavior.

Before relying on the feature in a normal deployment, manually verify it with a real authenticated session and a running backend: all six GIS toggles, attribution, loading/retry/error states, touch and keyboard use, map focus selection, and responsiveness with heavy layers on a phone/tablet-sized viewport.
