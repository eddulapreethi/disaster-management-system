-- Additive incident reporting and reviewer support.
-- Legacy Disaster rows retain NULL user_id and are excluded from incident APIs.
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS role VARCHAR(20) NOT NULL DEFAULT 'user';

ALTER TABLE disasters
    ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id),
    ADD COLUMN IF NOT EXISTS incident_time TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS incident_timezone VARCHAR(64),
    ADD COLUMN IF NOT EXISTS source VARCHAR(64) NOT NULL DEFAULT 'community_report',
    ADD COLUMN IF NOT EXISTS source_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS evidence_metadata JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS submitted_at TIMESTAMPTZ;

UPDATE disasters
SET submitted_at = created_at
WHERE submitted_at IS NULL;

ALTER TABLE disasters
    ALTER COLUMN status SET DEFAULT 'pending';

CREATE INDEX IF NOT EXISTS ix_disasters_user_id ON disasters (user_id);
CREATE INDEX IF NOT EXISTS ix_disasters_status_time ON disasters (status, incident_time);

CREATE TABLE IF NOT EXISTS disaster_report_reviews (
    id SERIAL PRIMARY KEY,
    disaster_id INTEGER NOT NULL REFERENCES disasters(id),
    reviewer_id INTEGER NOT NULL REFERENCES users(id),
    previous_status VARCHAR(30) NOT NULL,
    new_status VARCHAR(30) NOT NULL,
    note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_disaster_report_reviews_disaster_id
    ON disaster_report_reviews (disaster_id);
CREATE INDEX IF NOT EXISTS ix_disaster_report_reviews_reviewer_id
    ON disaster_report_reviews (reviewer_id);
