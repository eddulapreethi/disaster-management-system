# GIS-Derived ML Features

Store spatial features that are actually used as model inputs here, for example elevation, slope, population density, land-use class, distance to river or historical flood frequency. These are training/validation inputs, not display layers.

Map boundaries, roads, rivers and locations used for visualization belong under `gis/data/`. Record source, CRS (preferably WGS 84 / EPSG:4326 for exchange), units, extraction date and license. The current model pipeline still requires conversion into its declared feature schema; no sample feature data is included.
