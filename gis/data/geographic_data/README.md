# Geographic Data

This project’s default study area is Kochi, Kerala, India. The reference layers live in the category subfolders. They have been checked for file structure, WGS 84 coordinates, and overlap with the study-area bounding box; that does not establish positional accuracy, licensing, or fitness as flood-model inputs.

- Administrative boundaries, lakes, land use, rivers, and roads: Geofabrik India/Osm extracts (`southern-zone-latest-free.gpkg.zip`), filtered to the Kochi study bbox.
- Elevation: OpenTopography global DEM (`SRTMGL1`) for the same bbox. Confirm the applicable OpenTopography/SRTM redistribution terms; this project does not assert USGS 3DEP terms.
- Watersheds: HydroSHEDS HydroBASINS Asia, filtered by bbox. Verify the applicable attribution and redistribution terms before redistribution.

OpenTopography downloads require `OPENTOPOGRAPHY_API_KEY` in the local environment; the downloader intentionally does not contain or log an API key. The report omits credentials from the recorded source URL.

The readiness endpoint validates these files as reference GIS only. The risk map does not currently load them as static layers, and their presence does not make a flood forecast/model available. The OSM-derived features are selected by bbox but some polygon geometries extend beyond it; they are not clipped to the study boundary. Keep derived tables used for model training under `ml/datasets/gis/`; keep live application records in the database.
