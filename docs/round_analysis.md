# Classificação calculada e evolução por rodada

O limite cutoff_round X inclui as versões atuais dos jogos com matchday <= X.
Não reproduz o que era conhecido na data da rodada. Um adiado concluído depois
e uma correção recalculam os recortes afetados após coleta e dbt build.

## Modelos e grãos

- intermediate.int_team_match: duas contribuições por jogo elegível, uma por clube.
- mart.dim_season_teams: clubes presentes no calendário, inclusive sem resultados.
- mart.dim_rounds: calendário por fonte, competição, temporada e rodada.
- mart.team_round_performance: clube, limite de rodada e mando total/home/away.
- mart.standings_by_round: classificação e evolução por clube e limite de rodada.
- mart.round_summary: cobertura e resultados por rodada, incluindo rodadas vazias.

A raw real de BSA 2026 usa configuração de 20 clubes, 38 rodadas e 10 partidas
por rodada. Outras origens/temporadas usam o calendário observado; seus totais
esperados são nulos. Fixtures reduzidas não são apresentadas como campeonatos
completos. Os nomes de clubes usam a atualização de fonte mais recente disponível.

## Pontuação e recortes

Somente FINISHED com placares válidos e clubes distintos pontua. AWARDED, adiados,
cancelados e placares parciais não pontuam automaticamente. Vitória vale 3,
empate 1 e derrota 0. Eficiência = 100 * pontos / (3 * jogos), nula sem jogos.

Os acumulados são mantidos também para rodadas futuras; round_has_results permite
excluí-las de gráficos. Nunca somar points de vários cutoff_round para obter o
total da temporada. No painel, selecionar um único limite de rodada.

## Desempates e limitações

Referência: [REC Série A 2026, artigos 14 e 15](https://stcbfsiteprdimgbrs.blob.core.windows.net/img-site/cdn/REC_Brasileiro_Serie_A_2026_c984f8cf05.pdf),
consultado em 31/10/2026. O regulamento trata da classificação final; aplicar os
critérios disponíveis aos recortes intermediários é uma convenção deste projeto.

A ordenação usa pontos, vitórias, saldo e gols pró. Para BSA 2026, um empate
remanescente entre dois clubes usa pontos de confronto direto e depois saldo,
somente com uma partida de ida e outra de volta concluídas dentro do recorte.
Grupos remanescentes maiores não usam confronto direto.

Cartões e sorteio não estão disponíveis nos modelos. Empates não resolvidos
compartilham posição (1,2,2,4), com is_tie_unresolved e tie_reason.
team_id estabiliza display_order, sem servir de desempate esportivo.
position_change é posição anterior menos posição atual; positivo indica subida.
Sem rodada anterior, o valor é nulo.

is_official é sempre false. Punições administrativas e decisões sobre AWARDED
não são inferidas dos placares. Outras temporadas usam somente os critérios
básicos, com ranking_rules e motivo de empate explícitos.

Os totais sazonais reutilizam as mesmas contribuições por partida.
O ranking de ataque/defesa inclui somente clubes com jogos elegíveis; zero jogos
não deve colocar um clube entre as melhores defesas.
Consultas: queries/round_analysis.sql.

## Evidências da validação

- Suíte completa: 30 testes Python aprovados em PostgreSQL temporário.
- Após o filtro de ataque/defesa, o cenário de rodadas foi repetido e aprovado.
- Execução real: 15 modelos e 78 testes dbt aprovados, sem falhas ou itens ignorados.
- As 2.280 linhas acumuladas (20 clubes x 38 rodadas x 3 mandos) foram conferidas
  independentemente em Python, com jogos, vitórias, empates, derrotas,
  gols pró/contra, saldo e pontos iguais aos modelos.
- Classificação: 760 linhas; cobertura: 38 rodadas, 380 partidas e 328 finalizadas.
- Snapshot coletado em 31/10/2026, às 09h53 (Brasília).
- Relatório local: data/runs/f441b042-102f-493d-9a92-9487b9bb8883/report.json.
- Conferência local: data/runs/round-analysis-verification.json.
