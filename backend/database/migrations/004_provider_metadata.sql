-- Additive provenance storage for existing weather and hydrology observations.
-- Existing observation rows are preserved and receive an empty metadata object.
ALTER TABLE weather_observations
    ADD COLUMN IF NOT EXISTS provider_metadata JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE hydrological_observations
    ADD COLUMN IF NOT EXISTS provider_metadata JSONB NOT NULL DEFAULT '{}'::jsonb;
