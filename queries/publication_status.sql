-- Versão disponível aos consumidores e horário da ativação.
SELECT c.run_id, c.activated_at, p.created_at,
    jsonb_array_length(p.models) AS model_count
FROM ops.current_publication c JOIN ops.publications p USING (run_id);

-- Histórico de publicações/rollbacks.
SELECT event_id, run_id, activated_at
FROM ops.publication_events ORDER BY event_id DESC;

-- Versões do schema aplicadas.
SELECT version, checksum, applied_at FROM ops.schema_migrations ORDER BY version;
