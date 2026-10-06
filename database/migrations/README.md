# Database Migrations

Use a PostgreSQL database with PostGIS installed. Apply `001_enable_postgis.sql` before any schema script that uses `geography` or `geometry`. Run migrations and schema scripts against a dedicated database, after taking backups when data already exists.

The current backend does not run these SQL migrations automatically; its SQLAlchemy `create_all` setup remains separate. Do not assume running the FastAPI app applies these PostgreSQL/PostGIS scripts.
