SELECT 1 AS staging_is_empty
WHERE NOT EXISTS (
    SELECT 1
    FROM {{ ref('stg_matches') }}
)
