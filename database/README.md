# DisasterGuard AI Database

The SQL scripts here describe the runtime PostgreSQL/PostGIS application database. They are separate from `ml/datasets/` (training/evaluation inputs) and `gis/data/` (map display files). Do not commit a database dump or duplicate those datasets here.

## Apply the schema

Create a PostgreSQL database, ensure the PostGIS extension is available, then apply scripts from this directory in this order:

1. `migrations/001_enable_postgis.sql`
2. `schemas/users.sql`
3. `schemas/disasters.sql`
4. `schemas/weather_observations.sql`
5. `schemas/hydrological_observations.sql`
6. `schemas/hydrology_collection_state.sql`
7. `schemas/predictions.sql`
8. `schemas/alerts.sql`
9. `schemas/resources.sql`
10. `schemas/simulations.sql`
11. `schemas/locations.sql`

After the first FastAPI startup creates ORM tables, apply `migrations/002_hydrology_postgis.sql` on PostgreSQL to add the generated hydrology geography column and GiST index. SQLite local development does not use PostGIS.

For an existing weather table, review and apply `migrations/003_weather_observation_dedup.sql` before restarting the updated collector. It adds source/creation metadata and a database uniqueness constraint. The migration stops without deleting data if duplicate station/source/observation-time rows already exist; inspect and resolve those duplicates deliberately before rerunning it.

`seed_data/sample_data.sql` intentionally has no fabricated records. Add only authorized, clearly sourced development data.

## Configure FastAPI

Install backend requirements, then set `DATABASE_URL` in `backend/.env`, for example:

```dotenv
DATABASE_URL=postgresql+psycopg://db_user:db_password@localhost:5432/disasterguard_db
```

Do not put production credentials in source control. The backend currently defaults to SQLite when `DATABASE_URL` is unset and calls SQLAlchemy `create_all`; it does not automatically apply these PostGIS scripts or manage migrations. The SQL schema and ORM models must remain aligned before using this as a production database.

The `users` table has no role field. Spatial coordinates use WGS 84 / SRID 4326, while GeoJSON exchanges use `[longitude, latitude]` ordering.
