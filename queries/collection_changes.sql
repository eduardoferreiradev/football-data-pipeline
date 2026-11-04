-- Cada coleta, incluindo as que não detectaram alterações.
SELECT * FROM mart.collection_changes_summary
WHERE source = 'football-data.org' AND season_year = 2026
ORDER BY observed_at DESC;

-- Campo anterior e novo; baseline não representa mudanças detectadas.
SELECT run_id, observed_at AT TIME ZONE 'America/Sao_Paulo' AS observed_at_local,
    match_id, change_type, field_name, previous_value, current_value
FROM mart.match_changes
WHERE source = 'football-data.org' AND season_year = 2026
    AND change_type <> 'baseline'
ORDER BY observed_at DESC, match_id, field_name;
