CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS mart;

CREATE TABLE IF NOT EXISTS raw.matches (
    source TEXT NOT NULL DEFAULT 'football-data.org',
    competition_code TEXT NOT NULL,
    season_year INTEGER,
    match_id BIGINT NOT NULL,
    extracted_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL,
    PRIMARY KEY (source, match_id)
);

CREATE INDEX IF NOT EXISTS idx_raw_matches_competition
    ON raw.matches (competition_code, season_year);

CREATE INDEX IF NOT EXISTS idx_raw_matches_payload_gin
    ON raw.matches USING GIN (payload);
