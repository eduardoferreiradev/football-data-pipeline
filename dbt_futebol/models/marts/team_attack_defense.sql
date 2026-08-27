SELECT
    source,
    competition_code,
    season_year,
    team_id,
    team_name,
    matches_played,
    goals_for,
    goals_against,
    goal_difference,
    ROUND((goals_for::NUMERIC / NULLIF(matches_played, 0)), 2) AS goals_for_per_match,
    ROUND((goals_against::NUMERIC / NULLIF(matches_played, 0)), 2) AS goals_against_per_match,
    RANK() OVER (
        PARTITION BY source, competition_code, season_year
        ORDER BY goals_for DESC, goal_difference DESC
    ) AS attack_rank,
    RANK() OVER (
        PARTITION BY source, competition_code, season_year
        ORDER BY goals_against ASC, goal_difference DESC
    ) AS defense_rank
FROM {{ ref('team_performance') }}
