# Weather Training Data

The current weather observations snapshot is stored here. The canonical raw Open-Meteo archive and its acquisition manifest belong at `ml/datasets/raw_sources/open_meteo/archive.json` and `ml/datasets/raw_sources/open_meteo/archive.manifest.json`, which are the paths checked by the flood readiness service. Do not keep a second default copy under `datasets/weather/raw`.

Live or near-real-time observations must be fetched by a backend data-collection service and stored as application records. Historical raw data is not automatically training-ready: review source permissions, units, UTC dates, returned grid coordinates, spatial/model metadata availability, and gauge/catchment suitability before feature preparation. A manifest records provenance but does not establish licensing approval. No sample archive is included.
