# PostgreSQL/PostGIS Schemas

These SQL files define the runtime application database; they are not ML training datasets or a database server. The database server must exist separately, and PostGIS must be installed and enabled.

Apply `../migrations/001_enable_postgis.sql` first, then run `users.sql`, `disasters.sql`, `weather_observations.sql`, `hydrological_observations.sql`, `hydrology_collection_state.sql`, `predictions.sql`, `alerts.sql`, `resources.sql`, `simulations.sql`, and `locations.sql` in that order. Apply `../migrations/002_hydrology_postgis.sql` after the backend has created the ORM tables to add its PostgreSQL-only geography column and GiST index. Existing weather tables should use `../migrations/003_weather_observation_dedup.sql` to add source metadata and safe deduplication. Spatial coordinates use WGS 84 (`geography` SRID 4326); GeoJSON coordinate order is `[longitude, latitude]`.

The users table intentionally has no role column. Several tables retain the current SQLAlchemy model's names and required fields. These scripts are a PostgreSQL schema baseline; the backend currently creates ORM tables through `create_all` and defaults to SQLite unless configured, so applying these scripts does not itself switch or migrate the running backend. Keep the ORM definitions, migrations and database URL aligned before using these scripts for production data.
