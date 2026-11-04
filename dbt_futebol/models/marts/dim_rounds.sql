WITH datasets AS (
    SELECT source, competition_code, season_year, MAX(matchday) AS max_observed_round,
        MAX(extracted_at) AS latest_collected_at
    FROM {{ ref('stg_matches') }}
    GROUP BY source, competition_code, season_year
),
participants AS (
    SELECT source, competition_code, season_year, COUNT(*) AS observed_team_count
    FROM {{ ref('dim_season_teams') }} GROUP BY source, competition_code, season_year
),
configured AS (
    SELECT d.*, p.observed_team_count,
        source = 'football-data.org' AND competition_code = 'BSA' AND season_year = 2026
            AS uses_configured_calendar
    FROM datasets d JOIN participants p USING (source, competition_code, season_year)
)
SELECT c.source, c.competition_code, c.season_year, r.matchday,
    CASE WHEN uses_configured_calendar THEN 20 END AS expected_team_count,
    CASE WHEN uses_configured_calendar THEN 10 END AS expected_matches_per_round,
    observed_team_count, latest_collected_at,
    CASE WHEN uses_configured_calendar THEN 'configured' ELSE 'observed' END AS calendar_basis
FROM configured c
CROSS JOIN LATERAL generate_series(
    1, CASE WHEN uses_configured_calendar THEN 38 ELSE max_observed_round END
) r(matchday)
