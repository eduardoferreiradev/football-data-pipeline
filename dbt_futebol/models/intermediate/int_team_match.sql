WITH oriented AS (
    SELECT source, competition_code, season_year, match_id, matchday,
        home_team_id AS team_id, away_team_id AS opponent_id, 'home'::TEXT AS venue,
        home_score AS goals_for, away_score AS goals_against
    FROM {{ ref('stg_matches') }} WHERE is_eligible
    UNION ALL
    SELECT source, competition_code, season_year, match_id, matchday,
        away_team_id, home_team_id, 'away'::TEXT, away_score, home_score
    FROM {{ ref('stg_matches') }} WHERE is_eligible
)
SELECT *, 1 AS matches_played,
    CASE WHEN goals_for > goals_against THEN 1 ELSE 0 END AS wins,
    CASE WHEN goals_for = goals_against THEN 1 ELSE 0 END AS draws,
    CASE WHEN goals_for < goals_against THEN 1 ELSE 0 END AS losses,
    goals_for - goals_against AS goal_difference,
    CASE WHEN goals_for > goals_against THEN 3
         WHEN goals_for = goals_against THEN 1 ELSE 0 END AS points
FROM oriented
