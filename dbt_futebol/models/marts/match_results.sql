SELECT
    source,
    match_id,
    competition_code,
    season_year,
    match_datetime_utc,
    matchday,
    home_team_name,
    away_team_name,
    home_score,
    away_score,
    CASE
        WHEN home_score > away_score THEN home_team_name
        WHEN away_score > home_score THEN away_team_name
        WHEN home_score = away_score THEN 'Draw'
        ELSE NULL
    END AS result
FROM {{ ref('stg_matches') }}
WHERE status = 'FINISHED'
