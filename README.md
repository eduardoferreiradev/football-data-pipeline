# Brasileirão 2026 — pipeline de dados

Acompanha resultados e alterações da Série A com Python, PostgreSQL e dbt.
Base: main de eduardoferreiradev/football-data-pipeline, commit 0b6e21e.

Primeira execução completa verificada: [evidências](docs/first_execution.md).

## Executar

Requisitos: Docker Desktop iniciado. Copie .env.example para .env e configure
FOOTBALL_DATA_API_TOKEN. Porta local padrão 5434; rede e volume pertencem
exclusivamente ao projeto brasileirao-2026.

    docker compose run --build --rm pipeline

Sobe PostgreSQL, coleta BSA 2026, valida 380 jogos, 20 clubes e 38 rodadas,
prepara o schema, preserva observações, atualiza raw e executa dbt build.
Falhas retornam código diferente de zero.

data/runs/<execution_id>/response.json e report.json guardam a resposta e o
diagnóstico por etapa. Esses arquivos são locais e ignorados pelo Git.

    docker compose run --rm pipeline --sample
    docker compose run --rm pipeline --input data/runs/EXECUTION_ID/response.json

O sample é sintético, de 2025, separado por source=sample.

## Consistência e limites desta primeira entrega

- raw.matches guarda a versão mais recente por (source, match_id).
- raw.observations guarda cada observação e ops.runs registra a ingestão.
- Repetir um lote cria outra observação, sem duplicar partidas atuais.
- Partidas e sucesso da ingestão são transacionais. report.json distingue
  ingestão de sucesso completo, que também depende do dbt.
- Lote vazio, duplicatas, escopo errado e placares inválidos são rejeitados.
- Calendário incompleto bloqueia a execução; partidas ausentes não são apagadas.
- O histórico começa na primeira coleta preservada.
- dbt constrói uma geração isolada; somente depois dos testes o publicador troca
  as views dos marts em uma transação. Falhas preservam a publicação anterior.
- Migrações versionadas registram checksums e preservam o banco já existente.
- Consulte [publicação, migrações e rollback](docs/publication.md). A implementação
  foi validada em testes e aplicada ao banco local em 03/11/2026.

## Mudanças entre coletas

O relatório de cada nova execução inclui o resumo de alterações. Consulte
[as regras](docs/collection_changes.md) e [os exemplos SQL](queries/collection_changes.sql)
para ver campos anteriores e novos e distinguir baseline, partidas novas e ausentes.

## Classificação e rodadas

Os modelos incluem desempenho acumulado, classificação calculada e cobertura por
rodada. Consulte [regras e limitações](docs/round_analysis.md) e
[consultas prontas](queries/round_analysis.sql).

## Execução diária

O serviço scheduler executa diariamente às 6h de Brasília, com estado persistente
e tentativas limitadas. Consulte [ativação, diagnóstico e limites](docs/scheduling.md).

    docker compose --profile scheduled up -d --build scheduler

O computador e o Docker precisam estar ativos. Ao retornar, o serviço recupera o
ciclo pendente mais recente.

## Desenvolvimento

    python -m venv .venv
    .venv/Scripts/python.exe -m pip install -r requirements.txt -r requirements-dev.txt
    .venv/Scripts/python.exe -m pytest
    .venv/Scripts/ruff.exe check src tests

## Próximas entregas

1. Ampliar testes de integração para concorrência.
2. Revisar a entrega analítica e preparar visualização.
3. Retenção controlada de gerações e evolução dos alertas operacionais.
4. Painel e roteiro de demonstração.
