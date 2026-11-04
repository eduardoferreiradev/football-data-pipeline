CREATE TABLE ops.publications (
    run_id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    models JSONB NOT NULL
);
CREATE TABLE ops.current_publication (
    singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton),
    run_id UUID NOT NULL REFERENCES ops.publications(run_id),
    activated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE ops.publication_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES ops.publications(run_id),
    activated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
