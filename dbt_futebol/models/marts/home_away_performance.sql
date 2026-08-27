WITH team_matches AS (
    SELECT
        source,
        competition_code,
        season_year,
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
    FROM {{ ref('stg_matches') }}
    WHERE status = 'FINISHED'

    UNION ALL

    SELECT
        source,
        competition_code,
        season_year,
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
    FROM {{ ref('stg_matches') }}
    WHERE status = 'FINISHED'
)

SELECT
    source,
    competition_code,
    season_year,
    team_id,
    MAX(team_name) AS team_name,
    venue,
    COUNT(*) AS matches_played,
    SUM(wins) AS wins,
    SUM(draws) AS draws,
    SUM(losses) AS losses,
    SUM(goals_for) AS goals_for,
    SUM(goals_against) AS goals_against,
    SUM(goals_for - goals_against) AS goal_difference,
    SUM(points) AS points
FROM team_matches
GROUP BY source, competition_code, season_year, team_id, venue
ORDER BY source, competition_code, season_year, team_name, venue
