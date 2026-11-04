SELECT d.source, d.competition_code, d.season_year,
    r.matchday AS cutoff_round, d.team_id, d.team_name, v.venue,
    COALESCE(SUM(t.matches_played), 0) AS matches_played,
    COALESCE(SUM(t.wins), 0) AS wins, COALESCE(SUM(t.draws), 0) AS draws,
    COALESCE(SUM(t.losses), 0) AS losses,
    COALESCE(SUM(t.goals_for), 0) AS goals_for,
    COALESCE(SUM(t.goals_against), 0) AS goals_against,
    COALESCE(SUM(t.goal_difference), 0) AS goal_difference,
    COALESCE(SUM(t.points), 0) AS points,
    100.0 * SUM(t.points) / NULLIF(3 * SUM(t.matches_played), 0) AS efficiency_pct,
    r.latest_collected_at
FROM {{ ref('dim_season_teams') }} d
JOIN {{ ref('dim_rounds') }} r USING (source, competition_code, season_year)
CROSS JOIN (VALUES ('total'), ('home'), ('away')) v(venue)
LEFT JOIN {{ ref('int_team_match') }} t
    ON t.source = d.source AND t.competition_code = d.competition_code
    AND t.season_year = d.season_year AND t.team_id = d.team_id
    AND t.matchday <= r.matchday AND (v.venue = 'total' OR t.venue = v.venue)
GROUP BY d.source, d.competition_code, d.season_year, r.matchday, d.team_id,
    d.team_name, v.venue, r.latest_collected_at
