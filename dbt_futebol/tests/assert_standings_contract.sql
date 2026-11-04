SELECT * FROM {{ ref('standings_by_round') }}
WHERE position < 1 OR is_official
    OR is_tie_unresolved <> (remaining_tie_size > 1)
    OR (is_tie_unresolved AND tie_reason IS NULL)
    OR (NOT is_tie_unresolved AND tie_reason IS NOT NULL)
    OR (NOT head_to_head_complete AND (head_to_head_points <> 0 OR head_to_head_goal_difference <> 0))
