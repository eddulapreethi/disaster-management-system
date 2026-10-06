# DisasterGuard GIS Module

This module validates GeoJSON point, line and polygon layers, calculates great-circle distances, composes switchable risk/disaster/infrastructure/geographic layers, and creates interactive Folium maps (Leaflet with OpenStreetMap tiles).

## Install

From the project root:

```powershell
python -m pip install -r gis/requirements.txt
```

## Use

The backend's `GET /api/gis/risk-points` response can be passed directly as `risk_points`:

```python
from gis.visualization.map_generator import generate_map

map_object = generate_map(risk_points, "gis/output/risk-map.html")
```

GeoJSON point coordinates must follow the standard `[longitude, latitude]` order. Risk, disaster and infrastructure marker layers accept Point FeatureCollections. Geographic display layers may include Point, MultiPoint, LineString, MultiLineString, Polygon, MultiPolygon and GeometryCollection features. Use `gis.gis_processing.load_geojson` to load and validate supported geographic collections.

`gis/data/geographic_data/` is for authorized map display layers such as boundaries, roads, rivers, lakes and land use. `gis/data/location_data/` is for point locations such as hospitals and shelters. GIS-derived values actually used as model inputs belong under `ml/datasets/gis/`; operational predictions and resources belong in the application database. No fabricated map data is included.

Folium uses OpenStreetMap tiles by default, so viewing the generated map requires an internet connection for the basemap tiles.
