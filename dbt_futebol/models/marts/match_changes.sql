WITH ordered_runs AS (
    SELECT *,
        LAG(run_id) OVER (
            PARTITION BY source, competition_code, season_year
            ORDER BY observed_at, finished_at, run_id
        ) AS previous_run_id
    FROM {{ ref('stg_collection_runs') }}
),

pairs AS (
    SELECT r.run_id, r.previous_run_id, r.source, r.competition_code,
        r.season_year, r.observed_at, k.match_id,
        p.payload AS previous_payload, c.payload AS current_payload
    FROM ordered_runs r
    CROSS JOIN LATERAL (
        SELECT match_id FROM {{ ref('stg_match_observations') }}
        WHERE run_id = r.run_id AND source = r.source
        UNION
        SELECT match_id FROM {{ ref('stg_match_observations') }}
        WHERE run_id = r.previous_run_id AND source = r.source
    ) k
    LEFT JOIN {{ ref('stg_match_observations') }} c
        ON c.run_id = r.run_id AND c.source = r.source AND c.match_id = k.match_id
    LEFT JOIN {{ ref('stg_match_observations') }} p
        ON p.run_id = r.previous_run_id AND p.source = r.source AND p.match_id = k.match_id
),

expanded AS (
    SELECT p.run_id, p.previous_run_id, p.source, p.competition_code,
        p.season_year, p.observed_at, p.match_id,
        CASE
            WHEN previous_run_id IS NULL THEN 'baseline'
            WHEN previous_payload IS NULL THEN 'added'
            WHEN current_payload IS NULL THEN 'missing'
            ELSE 'updated'
        END AS change_type,
        f.field_name, f.previous_value, f.current_value
    FROM pairs p
    CROSS JOIN LATERAL (VALUES
        ('presence', to_jsonb(previous_payload IS NOT NULL), to_jsonb(current_payload IS NOT NULL)),
        ('status', previous_payload -> 'status', current_payload -> 'status'),
        ('scheduled_at', to_jsonb((previous_payload ->> 'utcDate')::TIMESTAMPTZ),
            to_jsonb((current_payload ->> 'utcDate')::TIMESTAMPTZ)),
        ('round', previous_payload -> 'matchday', current_payload -> 'matchday'),
        ('home_score', COALESCE(previous_payload #> '{score,fullTime,home}', 'null'::JSONB),
            COALESCE(current_payload #> '{score,fullTime,home}', 'null'::JSONB)),
        ('away_score', COALESCE(previous_payload #> '{score,fullTime,away}', 'null'::JSONB),
            COALESCE(current_payload #> '{score,fullTime,away}', 'null'::JSONB)),
        ('home_team_id', previous_payload #> '{homeTeam,id}', current_payload #> '{homeTeam,id}'),
        ('away_team_id', previous_payload #> '{awayTeam,id}', current_payload #> '{awayTeam,id}')
    ) f(field_name, previous_value, current_value)
    WHERE (
        f.field_name = 'presence'
        AND (previous_payload IS NULL OR current_payload IS NULL)
    ) OR (
        f.field_name <> 'presence'
        AND previous_payload IS NOT NULL AND current_payload IS NOT NULL
        AND f.previous_value IS DISTINCT FROM f.current_value
    )
)

SELECT * FROM expanded
