CREATE SCHEMA IF NOT EXISTS ops;
CREATE TABLE IF NOT EXISTS ops.runs (
 run_id UUID PRIMARY KEY, source TEXT NOT NULL, competition_code TEXT NOT NULL,
 season_year INTEGER NOT NULL, observed_at TIMESTAMPTZ NOT NULL,
 finished_at TIMESTAMPTZ, status TEXT NOT NULL
 CHECK (status IN ('running','succeeded','failed')),
 match_count INTEGER NOT NULL DEFAULT 0, changed_count INTEGER NOT NULL DEFAULT 0,
 error_type TEXT
);
CREATE TABLE IF NOT EXISTS raw.observations (
 run_id UUID REFERENCES ops.runs(run_id), source TEXT NOT NULL,
 match_id BIGINT NOT NULL, payload JSONB NOT NULL,
 PRIMARY KEY(run_id, source, match_id)
);
