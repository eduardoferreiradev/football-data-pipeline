SELECT
    source,
    competition_code,
    season_year,
    matchday,
    COUNT(*) AS matches_played,
    SUM(home_score + away_score) AS total_goals,
    ROUND(AVG(home_score + away_score)::NUMERIC, 2) AS avg_goals_per_match,
    SUM(CASE WHEN home_score > away_score THEN 1 ELSE 0 END) AS home_wins,
    SUM(CASE WHEN away_score > home_score THEN 1 ELSE 0 END) AS away_wins,
    SUM(CASE WHEN home_score = away_score THEN 1 ELSE 0 END) AS draws
FROM {{ ref('stg_matches') }}
WHERE status = 'FINISHED'
GROUP BY source, competition_code, season_year, matchday
ORDER BY source, competition_code, season_year, matchday
