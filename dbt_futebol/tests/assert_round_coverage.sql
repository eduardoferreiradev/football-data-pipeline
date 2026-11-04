SELECT d.source, d.competition_code, d.season_year, r.matchday, d.team_id
FROM {{ ref('dim_season_teams') }} d
JOIN {{ ref('dim_rounds') }} r USING (source, competition_code, season_year)
LEFT JOIN {{ ref('standings_by_round') }} s
    ON s.source=d.source AND s.competition_code=d.competition_code
    AND s.season_year=d.season_year AND s.cutoff_round=r.matchday AND s.team_id=d.team_id
WHERE s.team_id IS NULL
