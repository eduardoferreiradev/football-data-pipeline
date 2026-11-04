WITH base AS (
    SELECT *, COUNT(*) OVER (
        PARTITION BY source, competition_code, season_year, cutoff_round,
            points, wins, goal_difference, goals_for
    ) AS basic_tie_size
    FROM {{ ref('team_round_performance') }} WHERE venue = 'total'
),
head_to_head AS (
    SELECT b.source, b.competition_code, b.season_year, b.cutoff_round, b.team_id,
        COUNT(t.match_id) AS head_to_head_games,
        COUNT(t.match_id) FILTER (WHERE t.venue = 'home') AS home_legs,
        COUNT(t.match_id) FILTER (WHERE t.venue = 'away') AS away_legs,
        COALESCE(SUM(t.points), 0) AS head_to_head_points,
        COALESCE(SUM(t.goal_difference), 0) AS head_to_head_goal_difference
    FROM base b JOIN base o
        ON o.source = b.source AND o.competition_code = b.competition_code
        AND o.season_year = b.season_year AND o.cutoff_round = b.cutoff_round
        AND o.points = b.points AND o.wins = b.wins AND o.goal_difference = b.goal_difference
        AND o.goals_for = b.goals_for AND o.team_id <> b.team_id
    LEFT JOIN {{ ref('int_team_match') }} t
        ON t.source = b.source AND t.competition_code = b.competition_code
        AND t.season_year = b.season_year AND t.team_id = b.team_id
        AND t.opponent_id = o.team_id AND t.matchday <= b.cutoff_round
    WHERE b.basic_tie_size = 2 AND b.competition_code = 'BSA' AND b.season_year = 2026
    GROUP BY b.source, b.competition_code, b.season_year, b.cutoff_round, b.team_id
),
criteria AS (
    SELECT b.*, b.competition_code = 'BSA' AND b.season_year = 2026 AS uses_bsa_2026_rules,
        COALESCE(h.head_to_head_games, 0) AS head_to_head_games,
        COALESCE(h.home_legs = 1 AND h.away_legs = 1 AND h.head_to_head_games = 2, FALSE)
            AS head_to_head_complete,
        CASE WHEN h.home_legs = 1 AND h.away_legs = 1 AND h.head_to_head_games = 2
            THEN h.head_to_head_points ELSE 0 END AS head_to_head_points,
        CASE WHEN h.home_legs = 1 AND h.away_legs = 1 AND h.head_to_head_games = 2
            THEN h.head_to_head_goal_difference ELSE 0 END AS head_to_head_goal_difference
    FROM base b LEFT JOIN head_to_head h
        USING (source, competition_code, season_year, cutoff_round, team_id)
),
ranked AS (
    SELECT *, RANK() OVER (
        PARTITION BY source, competition_code, season_year, cutoff_round
        ORDER BY points DESC, wins DESC, goal_difference DESC, goals_for DESC,
            head_to_head_points DESC, head_to_head_goal_difference DESC
    ) AS position,
    ROW_NUMBER() OVER (
        PARTITION BY source, competition_code, season_year, cutoff_round
        ORDER BY points DESC, wins DESC, goal_difference DESC, goals_for DESC,
            head_to_head_points DESC, head_to_head_goal_difference DESC, team_id
    ) AS display_order,
    COUNT(*) OVER (
        PARTITION BY source, competition_code, season_year, cutoff_round,
            points, wins, goal_difference, goals_for,
            head_to_head_points, head_to_head_goal_difference
    ) AS remaining_tie_size
    FROM criteria
),
evolution AS (
    SELECT *, LAG(position) OVER (
        PARTITION BY source, competition_code, season_year, team_id ORDER BY cutoff_round
    ) AS previous_position FROM ranked
)
SELECT e.*, previous_position - position AS position_change,
    remaining_tie_size > 1 AS is_tie_unresolved,
    CASE WHEN remaining_tie_size = 1 THEN NULL
         WHEN NOT uses_bsa_2026_rules THEN 'unsupported_ruleset'
         WHEN basic_tie_size = 2 AND NOT head_to_head_complete THEN 'head_to_head_incomplete'
         ELSE 'cards_and_draw_unavailable' END AS tie_reason,
    CASE WHEN uses_bsa_2026_rules THEN 'bsa_2026_partial'
         ELSE 'basic_points_wins_gd_gf' END AS ranking_rules,
    FALSE AS is_official, r.matches_played > 0 AS round_has_results, r.round_status
FROM evolution e JOIN {{ ref('round_summary') }} r
    ON r.source = e.source AND r.competition_code = e.competition_code
    AND r.season_year = e.season_year AND r.matchday = e.cutoff_round
