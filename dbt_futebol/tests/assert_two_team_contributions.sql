SELECT m.source, m.match_id
FROM {{ ref('stg_matches') }} m
LEFT JOIN {{ ref('int_team_match') }} t USING (source, match_id)
WHERE m.is_eligible
GROUP BY m.source, m.match_id
HAVING COUNT(t.team_id) <> 2 OR SUM(t.goal_difference) <> 0
    OR SUM(t.wins) <> SUM(t.losses) OR SUM(t.goals_for) <> SUM(t.goals_against)
