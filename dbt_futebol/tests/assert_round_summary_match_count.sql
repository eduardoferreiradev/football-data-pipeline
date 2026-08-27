WITH finished_matches AS (
    SELECT
        source,
        competition_code,
        season_year,
        COUNT(*) AS match_count
    FROM {{ ref('stg_matches') }}
    WHERE status = 'FINISHED'
    GROUP BY source, competition_code, season_year
),

round_matches AS (
    SELECT
        source,
        competition_code,
        season_year,
        SUM(matches_played) AS match_count
    FROM {{ ref('round_summary') }}
    GROUP BY source, competition_code, season_year
)

SELECT
    COALESCE(finished_matches.source, round_matches.source) AS source,
    COALESCE(finished_matches.competition_code, round_matches.competition_code) AS competition_code,
    COALESCE(finished_matches.season_year, round_matches.season_year) AS season_year,
    COALESCE(finished_matches.match_count, 0) AS staging_match_count,
    COALESCE(round_matches.match_count, 0) AS round_summary_match_count
FROM finished_matches
FULL OUTER JOIN round_matches
    USING (source, competition_code, season_year)
WHERE COALESCE(finished_matches.match_count, 0) <> COALESCE(round_matches.match_count, 0)
