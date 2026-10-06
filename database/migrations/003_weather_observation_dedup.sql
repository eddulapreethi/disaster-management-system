BEGIN;

ALTER TABLE weather_observations
    ADD COLUMN IF NOT EXISTS source VARCHAR(64) NOT NULL DEFAULT 'open-meteo';
ALTER TABLE weather_observations
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM weather_observations
        GROUP BY station_id, observation_time, source
        HAVING COUNT(*) > 1
    ) THEN
        RAISE EXCEPTION 'Duplicate weather rows exist; resolve them before adding the weather uniqueness constraint.';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'uq_weather_station_source_time'
          AND conrelid = 'weather_observations'::regclass
    ) THEN
        ALTER TABLE weather_observations
            ADD CONSTRAINT uq_weather_station_source_time
            UNIQUE (station_id, observation_time, source);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_weather_station_observation
    ON weather_observations (station_id, observation_time);

COMMIT;