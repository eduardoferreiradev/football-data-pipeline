# Publicação consistente e migrações

## Caminho de uma execução

1. Validar a resposta e adquirir o lock global do pipeline.
2. Aplicar migrações versionadas.
3. Preservar observações e atualizar raw.
4. Construir e testar os modelos em build_<execution_id>_staging/intermediate/mart.
5. Validar manifest.json e run_results.json da mesma invocação.
6. Atualizar as views públicas e o marcador da publicação em uma transação.

Cada execução exige todos os modelos e testes habilitados. Falha, aviso, teste
ignorado, execução parcial ou artefatos de invocações diferentes bloqueiam a
publicação. Os artefatos ficam em data/runs/<execution_id>/dbt, no volume local.

## O que fica consistente

Os consumidores consultam mart.*. Essas views apontam para tabelas calculadas
da mesma geração aprovada. Um dbt build com falha pode atualizar a raw e deixar
schemas de construção incompletos; o mart público continua na última publicação.

staging.* e intermediate.* são auxiliares em views sobre a raw. A garantia de
snapshot dos resultados se aplica aos marts materializados, não à leitura da raw
ou desses auxiliares. A aplicação deve consumir os marts publicados.

A mudança das views, o histórico e o marcador da publicação têm um único commit.
Uma consulta SQL nova vê a geração publicada integralmente. Um relatório que faz
várias consultas independentes pode atravessar o instante do commit; para fixar
uma geração durante toda a leitura, usar uma transação REPEATABLE READ.

Na primeira publicação, tabelas físicas antigas são movidas para
legacy_<execution_id>_<schema>, sem exclusão, e substituídas por views públicas.
Views de consumidores que já apontavam diretamente para essas tabelas antigas
antes da conversão precisam ser revisadas, pois preservam a dependência anterior.
Nas publicações seguintes, CREATE OR REPLACE VIEW mantém a identidade das views.

Mudanças incompatíveis em nomes, ordem ou tipos de colunas são bloqueadas pelo
PostgreSQL. Alterar o conjunto de modelos também exige uma migração explícita
do contrato e revisão do publicador; não existe substituição forçada automática.

## Histórico e rollback

ops.publications registra a geração e suas relações.
ops.current_publication indica a versão ativa.
ops.publication_events registra ativações e rollbacks.

Consultar queries/publication_status.sql. Para reativar uma geração registrada:

    docker compose run --rm --entrypoint python pipeline -m src.publish --rollback UUID

O rollback usa o mesmo lock global das execuções. Não desfaz coletas ou
observações; troca as views dos marts para a geração escolhida. Assim, os dados
publicados podem ser anteriores à raw, com o marcador explícito da publicação.
O comando requer as tabelas da geração ainda existentes e contrato compatível.

Schemas antigos e builds reprovados são preservados para diagnóstico/rollback.
Não há exclusão automática nesta entrega. A retenção e a limpeza controlada são
uma etapa operacional pendente; não usar DROP CASCADE indiscriminadamente.

## Migrações

    docker compose run --rm --entrypoint python pipeline -m src.migrate

sql/01_schema.sql e sql/02_history.sql entram no registro como bootstrap
idempotente, permitindo adotar o banco já inicializado sem apagar dados.
Depois deles são aplicados, em ordem, os arquivos sql/migrations/*.sql.

ops.schema_migrations guarda caminho, SHA-256 e horário. Todas as migrações de
uma invocação compartilham transação e lock: uma falha reverte DDL e registro.
Execuções seguintes ignoram scripts já aplicados, mas rejeitam scripts
alterados ou ausentes. Evoluir o banco adicionando arquivos; não editar os
scripts registrados. A adoção supõe o schema conhecido do projeto, sem
certificar alterações manuais feitas anteriormente no banco.

Em produção, usar o pipeline completo. dbt build direto, sem build_namespace,
é reservado a bancos de desenvolvimento/testes e pode substituir views públicas.

Referência de compatibilidade:
[CREATE VIEW no PostgreSQL 16](https://www.postgresql.org/docs/16/sql-createview.html).

## Validação e situação da implantação

Foram validados 54 cenários Python: 50 passaram na execução completa e quatro
casos de preparação de artefatos foram corrigidos e aprovados no reteste.
A implementação inclui testes de adoção do banco legado, checksums, migração
com falha, publicação parcialmente executada, falha real do dbt, recuperação,
compatibilidade de views de consumidores e rollback.

A aplicação ao banco local foi autorizada e concluída em 03/11/2026.
Foram aplicadas e conferidas as três migrações, publicadas 15 views e preservadas
11 tabelas físicas anteriores no schema legacy da primeira publicação.

Os 15 modelos e 78 testes dbt passaram no banco real. A geração ativa é
68b87b9d-ecd8-4a08-a2b7-6e2848cddf53. O scheduler foi recriado com a imagem nova,
preservando o ciclo diário concluído e a próxima execução de 04/11 às 06h00
em America/Sao_Paulo, sem repetir a coleta de hoje.

Coleta da primeira publicação: 03/11/2026, às 11h38 (Brasília),
com 380 partidas e 330 finalizadas.

Evidência local: data/runs/publication-verification.json.
