WITH total_matches AS (
    SELECT
        team_id,
        matches_played
    FROM {{ ref('team_performance') }}
),

venue_matches AS (
    SELECT
        team_id,
        SUM(matches_played) AS matches_played
    FROM {{ ref('home_away_performance') }}
    GROUP BY team_id
)

SELECT
    total_matches.team_id,
    total_matches.matches_played AS total_matches_played,
    venue_matches.matches_played AS venue_matches_played
FROM total_matches
JOIN venue_matches USING (team_id)
WHERE total_matches.matches_played <> venue_matches.matches_played
