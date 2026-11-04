# Comparação entre coletas

mart.match_changes compara observações de ingestões bem-sucedidas, separadas por
source, competition_code e season_year. O grão é (run_id, match_id, field_name).
A comparação usa observed_at; finished_at e run_id estabilizam empates.

Tipos de evento:

- baseline: partidas da primeira observação disponível; não são mudanças detectadas.
- added: partida presente que não estava na observação anterior.
- missing: partida ausente que estava na observação anterior. Não apaga raw.matches.
- updated: valor de um campo monitorado alterado.

Campos: status, horário agendado, rodada, placares finais e IDs dos dois clubes.
Alterações apenas em lastUpdated, nomes, árbitros e outros metadados não geram
evento. Timestamp com outro fuso e mesmo instante também não é mudança.

mart.collection_changes_summary inclui todas as ingestões bem-sucedidas, mesmo
sem mudança. Partidas alteradas são contadas uma vez; field_change_count conta
campos e pode ser maior. As novas execuções usam o mesmo run_id no relatório
local e em ops.runs; execuções anteriores à implementação mantêm seus IDs antigos.

Replay conserva observed_at. Uma coleta antiga inserida depois ocupa sua posição
cronológica e pode alterar as comparações derivadas seguintes. Ela não substitui
raw mais recente. is_latest_observation identifica o horário mais recente (mais
de uma execução pode compartilhar esse horário em um replay).
changed_count em ops.runs conta alterações aplicáveis à raw; os marts comparam
observações, inclusive quando não atualizam raw.

Uma resposta incompleta do BSA continua bloqueada antes da ingestão e do dbt.
Seu report.json informa missing_match_ids comparando com IDs conhecidos na raw.
Ela não entra nos marts de comparação de ingestões bem-sucedidas.
Se o banco ainda não tem referência, não há IDs conhecidos para indicar ausências.

Consultas prontas: queries/collection_changes.sql.
O histórico é observado a partir das coletas preservadas e não reconstrói o
passado anterior. Agendamento e notificações ainda não estão implementados.

## Validação desta entrega

- 29 testes Python aprovados, incluindo os cenários em PostgreSQL temporário.
- Build real no Docker: 10 modelos e 60 testes dbt aprovados, sem erros.
- Cenários: placar, status, horário, rodada, metadados sem evento, ausência,
  retorno, falha transacional, replay antigo e isolamento entre origens.
- Resposta incompleta: IDs ausentes no relatório, sem ingestão parcial.
- Coleta real em 31/10/2026, às 09h21 (Brasília): 380 partidas,
  328 finalizadas, zero alterações nos campos monitorados.
- Relatório local: data/runs/6b117d56-a20e-4a00-85f3-c0bb67697613/report.json.
- O baseline histórico tem 380 partidas e não foi contado como alteração nova.
