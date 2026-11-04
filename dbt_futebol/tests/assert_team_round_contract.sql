SELECT * FROM {{ ref('team_round_performance') }}
WHERE matches_played <> wins + draws + losses OR points <> 3 * wins + draws
    OR goal_difference <> goals_for - goals_against
    OR matches_played < 0 OR goals_for < 0 OR goals_against < 0
    OR (matches_played = 0 AND efficiency_pct IS NOT NULL)
    OR (matches_played > 0 AND ABS(efficiency_pct - 100.0 * points / (3 * matches_played)) > 0.0000001)
