SELECT run_id, source, competition_code, season_year, observed_at,
    finished_at, match_count, changed_count
FROM {{ source('ops', 'runs') }}
WHERE status = 'succeeded'
