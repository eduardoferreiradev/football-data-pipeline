SELECT *
FROM {{ ref('stg_matches') }}
WHERE status = 'FINISHED'
  AND (home_score IS NULL OR away_score IS NULL)
