-- Additive diagnostics for existing PostgreSQL hydrology collection state.
-- Safe to re-run; existing observations and cursor state are preserved.
ALTER TABLE hydrology_collection_state
    ADD COLUMN IF NOT EXISTS records_returned INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS valid_records INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS newer_observation_found BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS last_error TEXT;
