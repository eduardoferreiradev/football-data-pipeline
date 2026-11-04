SELECT d.source, d.competition_code, d.season_year, d.team_id, d.team_name,

    COALESCE(SUM(t.matches_played), 0) AS matches_played,
    COALESCE(SUM(t.wins), 0) AS wins, COALESCE(SUM(t.draws), 0) AS draws,
    COALESCE(SUM(t.losses), 0) AS losses, COALESCE(SUM(t.goals_for), 0) AS goals_for,
    COALESCE(SUM(t.goals_against), 0) AS goals_against,
    COALESCE(SUM(t.goal_difference), 0) AS goal_difference,
    COALESCE(SUM(t.points), 0) AS points
FROM {{ ref('dim_season_teams') }} d

LEFT JOIN {{ ref('int_team_match') }} t
    ON t.source = d.source AND t.competition_code = d.competition_code
    AND t.season_year = d.season_year AND t.team_id = d.team_id

GROUP BY d.source, d.competition_code, d.season_year, d.team_id, d.team_name
