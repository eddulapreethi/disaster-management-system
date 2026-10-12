# Data Acquisition and Preparation Report

## Scope and result

This report inventories the data artifacts present and validated for the Kochi, Kerala study area (WGS 84 bbox: west 76.0, south 9.8, east 76.5, north 10.1). Checks establish file readability, basic coordinate/CRS validity, coverage overlap, schema, and content hashes as described below. They do not establish positional accuracy, licensing rights, flood-model suitability, or a calibrated forecast.

| Data family | Result | Permitted conclusion |
|---|---|---|
| Reference GIS | 7/7 GeoJSON/GeoTIFF files passed readiness checks | Reference files overlap the study bbox; no flood-model readiness implied |
| Weather snapshot | 76 unique rows exported from 325 stored rows | Historical point observations available; 249 duplicate observation keys excluded |
| CWC/NWDP hydrology snapshot | 17,957 rows exported | Telemetry history available, but currently stale at the source |
| EM-DAT historical events | Clean master and six category outputs with manifests | Historical event/impact analysis only; not local continuous flood labels |
| Satellite imagery | Not acquired or processed | No satellite-derived features, flood masks, or labels are available |
| Flood training dataset/model | Not ready | No verified 20-feature mapping, aligned labels, or trained artifact |

## Source data and license/attribution notes

### GIS reference layers

The download inventory is recorded in [`gis/data/geographic_data/download_report.json`](../gis/data/geographic_data/download_report.json). The OSM-derived GeoJSON layers originate from the Geofabrik India extract and record OpenStreetMap attribution/ODbL 1.0 in the acquisition report:

| Layer | File | Features | Recorded source |
|---|---|---:|---|
| Administrative boundaries | `administrative_boundaries/kochi_administrative_boundaries.geojson` | 12 | [Geofabrik India](https://download.geofabrik.de/asia/india.html) |
| Lakes/water polygons | `lakes/kochi_lakes.geojson` | 4,040 | Geofabrik India |
| Land use | `land_use/kochi_land_use.geojson` | 3,003 | Geofabrik India |
| Rivers/waterways | `rivers/kochi_rivers.geojson` | 1,809 | Geofabrik India |
| Roads | `roads/kochi_roads.geojson` | 36,521 | Geofabrik India |
| Elevation | `elevation/kochi_dem.tif` | 1,800 x 1,080 raster | OpenTopography `SRTMGL1` |
| Watersheds | `watersheds/kochi_watersheds.geojson` | 2 | HydroSHEDS HydroBASINS Asia level 6 |

The six vector files declare WGS 84/CRS84 or EPSG:4326 and contain valid finite longitude/latitude coordinate pairs within world bounds. Their extents overlap the Kochi bbox. Features selected by bbox are not necessarily clipped to it; administrative and watershed polygons in particular can extend beyond the study area. The DEM declares EPSG:4326, has approximately 0.00027778-degree pixels (about one arc-second), nodata -32768, and bounds approximately 75.999861..76.499861 E, 9.800139..10.100139 N. Runtime validation sampled valid elevation cells; reported pixel values range from -34 to 106 m.

License caution: OSM requires attribution and ODbL compliance. The downloader records HydroSHEDS as a public basin-boundary source, but redistribution obligations should be checked against the current provider terms. The DEM is SRTMGL1; the earlier report's USGS 3DEP license assertion was corrected because that is not the selected DEM product. Confirm the applicable OpenTopography and SRTM source-data terms before redistribution. The download script now requires `OPENTOPOGRAPHY_API_KEY` from the local environment and omits the credential from the saved source URL; no key is stored in the report. The GeoJSON/GeoTIFF assets are not currently loaded as static layers by the risk map (`risk_map_uses_static_layers=false`).

The runtime validator checks geometry structure/coordinates and bbox intersection, GeoJSON feature counts, and DEM readability, CRS, dimensions, resolution, nodata, bounds, and sampled values. It does not perform full topology validation, positional-accuracy assessment, raster void/interpolation analysis, source-license verification, or hydrologic suitability validation.

### Weather and hydrology observations

The snapshot exporter [`ml/preprocessing/export_environmental_snapshots.py`](../ml/preprocessing/export_environmental_snapshots.py) reads stored observations, normalizes times to UTC, validates coordinate ranges, sorts deterministically, removes duplicate `(station_id, observation_time, source)` keys, and writes a CSV and manifest. It does not alter the database.

| Snapshot | Output | Exported rows | Source rows | Excluded duplicates | SHA-256 |
|---|---|---:|---:|---:|---|
| Weather | `ml/datasets/weather/processed/weather_observations.csv` | 76 | 325 | 249 | `f2d2213bd6e8365f91a223812aca345f71dbf772dec84390e2063c2ddee1e336` |
| Hydrology | `ml/datasets/hydrological/processed/hydrology_observations.csv` | 17,957 | 17,957 | 0 | `1e703f6d8825f2607ebdab60ea1d1cf1685fe426148a3f18a1e3e85a7693045c` |

Each output has a neighboring `.manifest.json` with column definitions/units, time and geographic coverage, missing-value counts, validation metrics, source URL, and the exact output hash. Weather is from Open-Meteo; hydrology is from the configured public NWDP CKAN/CWC resources. Provider redistribution terms have not been verified for these exports; do not redistribute them until the applicable terms are confirmed. The two files are station/point observations, not gridded surfaces; the records have not been spatially and temporally joined to event labels. No measurement is imputed, and unavailable discharge remains null.

To reproduce the snapshot from the intended configured database, run at the repository root:

```powershell
python -m ml.preprocessing.export_environmental_snapshots
```

The saved hash identifies the artifacts at report time. Re-exporting against a database with changed observations or fetch timestamps will produce updated files/manifests and hashes.

### EM-DAT event history

The supplied EM-DAT workbook is retained unchanged under `ml/datasets/historical_disasters/EM-DAT/`. The cleaned event table is `ml/datasets/historical_data/processed/emdat_cleaned.csv` (10,902 rows, 50 columns). Category outputs are:

| Output | Rows |
|---|---:|
| `floods.csv` | 4,291 |
| `glacial_lake_outburst_floods.csv` | 8 |
| `storms_cyclones.csv` | 2,929 |
| `landslides.csv` | 519 |
| `wildfires.csv` | 356 |
| `earthquakes.csv` | 707 |

Every category CSV has a companion manifest with input/source hashes, category selection, date and coordinate coverage, missing-value counts, and a training-suitability limitation. Glacial lake outburst floods are kept separate from general Flood records; event subtype/classification remains source-defined. The source filename contains `2026-09-30`, but does not prove the workbook retrieval date. The manifests therefore report retrieval date as unknown and store the filename date separately. EM-DAT access terms depend on the supplied academic/research request; the pipeline does not grant or confirm redistribution rights.

Rebuild cleaned and categorized artifacts with:

```powershell
python -m ml.preprocessing.historical_disasters.clean_emdat
python -m ml.preprocessing.historical_disasters.filter_disasters
```

EM-DAT records describe reported disaster events and impacts, often at event-level geography and time. They do not provide aligned non-event observations or a verified local inundation/probability target. They must not be treated as continuous flood-probability labels or as environmental predictors.

## Data not available

- No satellite products, flood masks, or satellite-derived features were acquired. Copernicus credentials in the example configuration are blank and no imagery export is present.
- No verified local flood/non-flood labels are joined to observations.
- No documented source/units/transformation mapping exists for the legacy 20-index input array.
- No current compatible trained flood-model artifact or verified runtime builder is available.
- GIS reference layers are not wired into the frontend as static flood layers.

Therefore the data-preparation artifacts support inspection and reproducible analysis only; they do not enable flood inference. See [`HYDROLOGY_AND_DATA_PIPELINE_STATUS.md`](./HYDROLOGY_AND_DATA_PIPELINE_STATUS.md) for the detailed live-source diagnosis and explicit readiness blockers.
