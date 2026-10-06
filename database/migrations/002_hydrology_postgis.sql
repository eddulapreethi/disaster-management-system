CREATE EXTENSION IF NOT EXISTS postgis;

-- The backend ORM creates the hydrology table for both SQLite and PostgreSQL.
-- This migration adds the PostgreSQL-only spatial column after the first backend
-- startup has created the table. It is generated from the stored WGS84 coordinates.
ALTER TABLE hydrological_observations
    ADD COLUMN IF NOT EXISTS geometry geography(Point, 4326)
    GENERATED ALWAYS AS (
        CASE
            WHEN latitude IS NULL OR longitude IS NULL THEN NULL::geography
            ELSE ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography
        END
    ) STORED;

CREATE INDEX IF NOT EXISTS ix_hydrological_observations_geometry
    ON hydrological_observations USING GIST (geometry);
