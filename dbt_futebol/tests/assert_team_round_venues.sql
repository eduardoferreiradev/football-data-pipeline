SELECT source, competition_code, season_year, cutoff_round, team_id
FROM {{ ref('team_round_performance') }}
GROUP BY source, competition_code, season_year, cutoff_round, team_id
HAVING SUM(CASE WHEN venue='total' THEN matches_played ELSE -matches_played END) <> 0
    OR SUM(CASE WHEN venue='total' THEN points ELSE -points END) <> 0
    OR SUM(CASE WHEN venue='total' THEN goals_for ELSE -goals_for END) <> 0
    OR SUM(CASE WHEN venue='total' THEN goals_against ELSE -goals_against END) <> 0
    OR COUNT(*) <> 3
