WITH appearances AS (
    SELECT source, competition_code, season_year, match_id,
        extracted_at, source_updated_at, home_team_id AS team_id, home_team_name AS team_name
    FROM {{ ref('stg_matches') }}
    UNION ALL
    SELECT source, competition_code, season_year, match_id,
        extracted_at, source_updated_at, away_team_id, away_team_name
    FROM {{ ref('stg_matches') }}
),
ranked AS (
    SELECT *, ROW_NUMBER() OVER (
        PARTITION BY source, competition_code, season_year, team_id
        ORDER BY source_updated_at DESC NULLS LAST, extracted_at DESC, match_id DESC, team_name
    ) AS name_order FROM appearances
)
SELECT source, competition_code, season_year, team_id, team_name,
    extracted_at AS latest_observed_at
FROM ranked WHERE name_order = 1
