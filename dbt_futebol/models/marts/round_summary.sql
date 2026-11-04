WITH counts AS (
    SELECT r.source, r.competition_code, r.season_year, r.matchday,
        r.expected_matches_per_round AS matches_expected, r.latest_collected_at,
        COUNT(m.match_id) AS matches_received,
        COUNT(m.match_id) FILTER (WHERE m.is_eligible) AS matches_played,
        COUNT(m.match_id) FILTER (WHERE NOT m.is_eligible) AS pending_received,
        COUNT(m.match_id) FILTER (WHERE m.status = 'POSTPONED') AS postponed_received,
        COUNT(m.match_id) FILTER (WHERE m.status = 'AWARDED') AS awarded_received,
        COALESCE(SUM(m.home_score + m.away_score) FILTER (WHERE m.is_eligible), 0) AS total_goals,
        ROUND(AVG(m.home_score + m.away_score) FILTER (WHERE m.is_eligible)::NUMERIC, 2)
            AS avg_goals_per_match,
        COUNT(m.match_id) FILTER (WHERE m.is_eligible AND m.home_score > m.away_score) AS home_wins,
        COUNT(m.match_id) FILTER (WHERE m.is_eligible AND m.away_score > m.home_score) AS away_wins,
        COUNT(m.match_id) FILTER (WHERE m.is_eligible AND m.home_score = m.away_score) AS draws
    FROM {{ ref('dim_rounds') }} r
    LEFT JOIN {{ ref('stg_matches') }} m USING (source, competition_code, season_year, matchday)
    GROUP BY r.source, r.competition_code, r.season_year, r.matchday,
        r.expected_matches_per_round, r.latest_collected_at
)
SELECT *,
    CASE WHEN matches_expected IS NOT NULL
        THEN GREATEST(matches_expected - matches_received, 0) END AS missing_matches,
    CASE WHEN matches_expected IS NULL THEN 'unknown'
         WHEN matches_received > matches_expected THEN 'excess'
         WHEN matches_received = matches_expected AND matches_played = matches_expected THEN 'complete'
         ELSE 'incomplete' END AS round_status
FROM counts
