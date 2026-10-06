CREATE TABLE IF NOT EXISTS hydrology_collection_state (
    source VARCHAR(160) PRIMARY KEY,
    source_resource_id VARCHAR(80),
    status VARCHAR(20) NOT NULL DEFAULT 'UNAVAILABLE',
    message TEXT,
    last_checked_at TIMESTAMPTZ,
    last_successful_fetch_at TIMESTAMPTZ,
    last_observation_at TIMESTAMPTZ,
    source_record_high_watermark BIGINT,
    records_received INTEGER NOT NULL DEFAULT 0,
    inserted_count INTEGER NOT NULL DEFAULT 0,
    duplicates_skipped INTEGER NOT NULL DEFAULT 0,
    parse_errors INTEGER NOT NULL DEFAULT 0
);
