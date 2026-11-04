SELECT r.run_id, r.source, r.competition_code, r.season_year,
    r.observed_at, o.match_id, o.payload
FROM {{ source('raw', 'observations') }} o
JOIN {{ ref('stg_collection_runs') }} r USING (run_id, source)
