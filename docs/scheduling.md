# Execução diária local

O serviço scheduler do Docker Compose chama o mesmo pipeline manual. Padrão:
06h00 em America/Sao_Paulo, até três tentativas operacionais por ciclo, com
intervalo de cinco minutos após o término da tentativa anterior.

Ativar:

    docker compose --profile scheduled up -d --build scheduler

Inspecionar:

    docker compose --profile scheduled logs --tail 20 scheduler
    docker compose exec -T scheduler python -m src.scheduler --status

Parar:

    docker compose stop scheduler

O computador precisa estar ligado, e o Docker Desktop precisa estar ativo.
restart: unless-stopped permite retorno com o Docker, exceto após parada manual.
Não foi alterada a configuração de inicialização do Windows/Docker Desktop.

## Retomada e falhas

- O status persistido em data/operations/status.json impede repetir o ciclo
  diário que já teve sucesso. A referência é scheduled_for, distinta de observed_at.
- Ao voltar de uma interrupção, executa o horário pendente mais recente; não
  simula coletas históricas dos dias em que o computador esteve desligado.
- Falha operacional permite novas tentativas. Erro de configuração ou validação
  encerra o ciclo e exige análise; no próximo dia haverá um ciclo novo.
- Falhas definitivas definem needs_attention=true. Os avisos são locais, no arquivo
  de status e nos logs; não há envio de email, mensagem ou notificação externa.
- events.jsonl preserva as transições. Cada tentativa tem execution_id, log e
  report.json. Dados operacionais são ignorados no Git e na imagem Docker.
- Se o processo cair com status running, ele retoma como tentativa interrompida,
  respeitando o limite de tentativas. Coletas podem gerar outra observação, mas
  não duplicam partidas.
- Um lock de arquivo impede dois schedulers de usar o mesmo diretório.
- O pipeline mantém um lock de sessão PostgreSQL durante schema, ingestão e dbt.
  Se outro pipeline estiver ativo, registra skipped e o scheduler pode tentar depois.
- dbt tem timeout padrão de 30 minutos. Ingestão bem-sucedida e execução completa
  continuam sendo estados diferentes. O publicador só ativa a geração após todos\n  os testes, em uma transação; consulte docs/publication.md.

Configuração: PIPELINE_TIMEZONE, PIPELINE_DAILY_HOUR, PIPELINE_DAILY_MINUTE,
PIPELINE_MAX_ATTEMPTS, PIPELINE_RETRY_SECONDS e DBT_TIMEOUT_SECONDS no .env.
Após alterar, recriar o scheduler com o comando de ativação.

Falhas: leia error_type, stage e retryable no report.json e o log indicado por
log_path. Após corrigir um problema persistente, uma coleta pode ser executada
manualmente; o agendador preserva o registro da falha daquele ciclo diário.
Não apague o status para ocultar falhas. O ciclo seguinte poderá executar normalmente.

Referência: [serviços do Docker Compose](https://docs.docker.com/reference/compose-file/services/).

## Validação da ativação

- 45 testes Python aprovados, incluindo banco temporário e relógio controlado.
- Serviço ativado no Docker; a primeira coleta pendente terminou na tentativa 1.
- 15 modelos e 78 testes dbt aprovados na execução agendada.
- Segunda instância bloqueada no Linux, com código de saída 2.
- Reinício do container preservou execution_id e status, sem repetir a coleta.
- Um único registro de ingestão para essa execução; raw manteve 380 partidas.
- Coleta em 31/10/2026, às 10h47 (Brasília).
- Evidência local ignorada no Git: data/operations/verification.json.
