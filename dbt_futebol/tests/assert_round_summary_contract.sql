SELECT * FROM {{ ref('round_summary') }}
WHERE matches_received <> matches_played + pending_received
    OR matches_played <> home_wins + away_wins + draws
    OR (matches_played = 0 AND avg_goals_per_match IS NOT NULL)
    OR (round_status = 'complete' AND (
        matches_expected IS NULL OR matches_played <> matches_expected
        OR matches_received <> matches_expected
    ))
    OR (matches_expected IS NULL AND (missing_matches IS NOT NULL OR round_status <> 'unknown'))
