SELECT r.run_id, r.source, r.competition_code, r.season_year, r.observed_at,
    r.match_count,
    r.observed_at = MAX(r.observed_at) OVER (
        PARTITION BY r.source, r.competition_code, r.season_year
    ) AS is_latest_observation,
    COUNT(DISTINCT c.match_id) FILTER (WHERE c.change_type = 'baseline') AS baseline_matches,
    COUNT(DISTINCT c.match_id) FILTER (WHERE c.change_type = 'added') AS added_matches,
    COUNT(DISTINCT c.match_id) FILTER (WHERE c.change_type = 'missing') AS missing_matches,
    COUNT(DISTINCT c.match_id) FILTER (WHERE c.change_type = 'updated') AS updated_matches,
    COUNT(*) FILTER (WHERE c.change_type = 'updated') AS field_change_count
FROM {{ ref('stg_collection_runs') }} r
LEFT JOIN {{ ref('match_changes') }} c USING (run_id, source, competition_code, season_year)
GROUP BY r.run_id, r.source, r.competition_code, r.season_year,
    r.observed_at, r.match_count
