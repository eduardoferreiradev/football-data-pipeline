-- Tabela de desempenho dos times
SELECT *
FROM mart.team_performance;

-- Jogos finalizados com resultado calculado
SELECT *
FROM mart.match_results
ORDER BY match_datetime_utc;

-- Times com melhor saldo de gols
SELECT
    team_name,
    goal_difference,
    goals_for,
    goals_against
FROM mart.team_performance
ORDER BY goal_difference DESC, goals_for DESC;

-- Times com melhor campanha como mandante
SELECT *
FROM mart.home_away_performance
WHERE venue = 'home'
ORDER BY points DESC, goal_difference DESC, goals_for DESC;

-- Times com melhor campanha como visitante
SELECT *
FROM mart.home_away_performance
WHERE venue = 'away'
ORDER BY points DESC, goal_difference DESC, goals_for DESC;

-- Rodadas com mais gols
SELECT *
FROM mart.round_summary
ORDER BY total_goals DESC, avg_goals_per_match DESC;

-- Ranking de ataque
SELECT
    team_name,
    goals_for,
    goals_for_per_match,
    attack_rank
FROM mart.team_attack_defense
ORDER BY attack_rank;

-- Ranking de defesa
SELECT
    team_name,
    goals_against,
    goals_against_per_match,
    defense_rank
FROM mart.team_attack_defense
ORDER BY defense_rank;
