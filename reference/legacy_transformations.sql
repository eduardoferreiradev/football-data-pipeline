CREATE OR REPLACE VIEW staging.matches AS
SELECT
    match_id,
    competition_code,
    season_year,
    extracted_at,
    (payload ->> 'utcDate')::TIMESTAMPTZ AS match_datetime_utc,
    payload ->> 'status' AS status,
    NULLIF(payload ->> 'matchday', '')::INTEGER AS matchday,
    payload ->> 'stage' AS stage,
    NULLIF(payload #>> '{homeTeam,id}', '')::BIGINT AS home_team_id,
    payload #>> '{homeTeam,name}' AS home_team_name,
    NULLIF(payload #>> '{awayTeam,id}', '')::BIGINT AS away_team_id,
    payload #>> '{awayTeam,name}' AS away_team_name,
    NULLIF(payload #>> '{score,fullTime,home}', '')::INTEGER AS home_score,
    NULLIF(payload #>> '{score,fullTime,away}', '')::INTEGER AS away_score,
    payload #>> '{score,winner}' AS winner
FROM raw.matches;

CREATE OR REPLACE VIEW mart.match_results AS
SELECT
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
FROM staging.matches
WHERE status = 'FINISHED';

CREATE OR REPLACE VIEW mart.team_performance AS
WITH team_matches AS (
    SELECT
        home_team_id AS team_id,
        home_team_name AS team_name,
        'home' AS venue,
        home_score AS goals_for,
        away_score AS goals_against,
        CASE
            WHEN home_score > away_score THEN 3
            WHEN home_score = away_score THEN 1
            ELSE 0
        END AS points,
        CASE WHEN home_score > away_score THEN 1 ELSE 0 END AS wins,
        CASE WHEN home_score = away_score THEN 1 ELSE 0 END AS draws,
        CASE WHEN home_score < away_score THEN 1 ELSE 0 END AS losses
    FROM staging.matches
    WHERE status = 'FINISHED'

    UNION ALL

    SELECT
        away_team_id AS team_id,
        away_team_name AS team_name,
        'away' AS venue,
        away_score AS goals_for,
        home_score AS goals_against,
        CASE
            WHEN away_score > home_score THEN 3
            WHEN away_score = home_score THEN 1
            ELSE 0
        END AS points,
        CASE WHEN away_score > home_score THEN 1 ELSE 0 END AS wins,
        CASE WHEN away_score = home_score THEN 1 ELSE 0 END AS draws,
        CASE WHEN away_score < home_score THEN 1 ELSE 0 END AS losses
    FROM staging.matches
    WHERE status = 'FINISHED'
)
SELECT
    team_id,
    team_name,
    COUNT(*) AS matches_played,
    SUM(wins) AS wins,
    SUM(draws) AS draws,
    SUM(losses) AS losses,
    SUM(goals_for) AS goals_for,
    SUM(goals_against) AS goals_against,
    SUM(goals_for - goals_against) AS goal_difference,
    SUM(points) AS points
FROM team_matches
GROUP BY team_id, team_name
ORDER BY points DESC, goal_difference DESC, goals_for DESC;
