SELECT * FROM {{ ref('match_changes') }}
WHERE (change_type = 'baseline' AND previous_run_id IS NOT NULL)
    OR (change_type <> 'baseline' AND previous_run_id IS NULL)
    OR (change_type = 'updated' AND (
        field_name = 'presence' OR previous_value IS NOT DISTINCT FROM current_value
    ))
    OR (change_type IN ('baseline', 'added', 'missing') AND field_name <> 'presence')
    OR (change_type = 'missing' AND (
        previous_value <> 'true'::JSONB OR current_value <> 'false'::JSONB
    ))
    OR (change_type IN ('baseline', 'added') AND (
        previous_value <> 'false'::JSONB OR current_value <> 'true'::JSONB
    ))
