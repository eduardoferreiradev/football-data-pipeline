WITH total_matches AS (
    SELECT
        source,
        competition_code,
        season_year,
        team_id,
        matches_played
    FROM {{ ref('team_performance') }}
),

venue_matches AS (
    SELECT
        source,
        competition_code,
        season_year,
        team_id,
        SUM(matches_played) AS matches_played
    FROM {{ ref('home_away_performance') }}
    GROUP BY source, competition_code, season_year, team_id
)

SELECT
    COALESCE(total_matches.source, venue_matches.source) AS source,
    COALESCE(total_matches.competition_code, venue_matches.competition_code) AS competition_code,
    COALESCE(total_matches.season_year, venue_matches.season_year) AS season_year,
    COALESCE(total_matches.team_id, venue_matches.team_id) AS team_id,
    COALESCE(total_matches.matches_played, 0) AS total_matches_played,
    COALESCE(venue_matches.matches_played, 0) AS venue_matches_played
FROM total_matches
FULL OUTER JOIN venue_matches
    USING (source, competition_code, season_year, team_id)
WHERE COALESCE(total_matches.matches_played, 0) <> COALESCE(venue_matches.matches_played, 0)
