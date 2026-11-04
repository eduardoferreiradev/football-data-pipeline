WITH latest AS (
    SELECT source, competition_code, season_year, MAX(matchday) AS cutoff_round
    FROM mart.round_summary WHERE matches_played > 0
    GROUP BY source, competition_code, season_year
)
SELECT s.cutoff_round, s.position, s.team_name, s.points, s.matches_played,
    s.wins, s.draws, s.losses, s.goals_for, s.goals_against, s.goal_difference,
    s.efficiency_pct, s.is_tie_unresolved, s.tie_reason
FROM mart.standings_by_round s JOIN latest
    USING (source, competition_code, season_year, cutoff_round)
WHERE s.source='football-data.org' AND s.competition_code='BSA' AND s.season_year=2026
ORDER BY s.display_order;

SELECT cutoff_round, position, points, matches_played, position_change
FROM mart.standings_by_round
WHERE source='football-data.org' AND season_year=2026 AND team_id=TEAM_ID
    AND round_has_results
ORDER BY cutoff_round;

SELECT * FROM mart.round_summary
WHERE source='football-data.org' AND season_year=2026
ORDER BY matchday;
