# Geographic Data

Store authorized map-display datasets here, including administrative boundaries, roads, rivers, lakes and land-use layers in the corresponding subfolders. Keep provider, license, coordinate reference system, publication/update date and transformation history documented with each dataset.

The GIS renderer accepts GeoJSON Point, MultiPoint, LineString, MultiLineString, Polygon, MultiPolygon and GeometryCollection features in WGS 84 longitude/latitude coordinates. Keep derived tables used for model training under `ml/datasets/gis/`; keep live application records in the database. No sample geographic data is included.
