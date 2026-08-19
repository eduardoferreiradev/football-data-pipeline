WITH finished_matches AS (
    SELECT COUNT(*) AS match_count
    FROM {{ ref('stg_matches') }}
    WHERE status = 'FINISHED'
),

round_matches AS (
    SELECT SUM(matches_played) AS match_count
    FROM {{ ref('round_summary') }}
)

SELECT *
FROM finished_matches
CROSS JOIN round_matches
WHERE finished_matches.match_count <> round_matches.match_count
