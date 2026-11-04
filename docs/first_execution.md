# Primeiro marco verificado

O pipeline foi executado dentro do Docker, consultando a API com season=2026.
Foram carregadas 380 partidas, 20 clubes e 38 rodadas. Nesse snapshot, 328 partidas
estavam finalizadas; cobertura do calendário não significa temporada encerrada.

- 27 testes Python passaram, incluindo integração em banco temporário exclusivo.
- 6 modelos e 50 testes do dbt passaram, sem erros ou itens ignorados.
- Reprocessamento da mesma resposta também passou no dbt.
- O banco manteve 380 partidas atuais e passou a ter 760 observações.
- A primeira ingestão registrou 380 mudanças; a repetição registrou zero.
- Payloads atuais foram comparados integralmente à resposta original em UTF-8.
- Jogos e pontos agregados dos clubes foram conferidos contra os placares.

Arquivos locais ignorados pelo Git:

- data/runs/a62ccfbb-29ec-4bf4-982c-b162578fa3d1/response.json
- data/runs/a62ccfbb-29ec-4bf4-982c-b162578fa3d1/report.json
- data/runs/8a0a2e65-a413-4ed1-b891-e6338a8c8a3f/report.json
- data/runs/verification.json

Para nova coleta, na pasta do projeto:

    docker compose run --rm pipeline

Isso inicia outra execução manual. Agendamento, painel e publicação consistente
continuam sendo etapas seguintes. O projeto anterior permanece separado.
