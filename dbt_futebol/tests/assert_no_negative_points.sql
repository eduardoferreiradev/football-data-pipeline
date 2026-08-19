SELECT *
FROM {{ ref('team_performance') }}
WHERE points < 0
