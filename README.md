# Pipeline de Dados de Futebol

Projeto inicial de engenharia de dados usando futebol como domínio.

O objetivo é entender o caminho dos dados entre sistemas:

```text
API football-data.org
  -> extrator Python
  -> PostgreSQL raw
  -> dbt staging
  -> dbt marts
  -> consultas analíticas
```

## Conceitos do Projeto

### Raw

Camada que guarda o dado bruto, quase do jeito que veio da fonte.

Tabela:

```text
raw.matches
```

Ela guarda cada partida como JSON em `payload`. Isso preserva o dado original.

### Staging

Camada que transforma o JSON em colunas limpas.

View:

```text
staging.stg_matches
```

Exemplo de colunas:

```text
match_id
match_datetime_utc
home_team_name
away_team_name
home_score
away_score
status
```

### Mart

Camada pronta para análise.

Tabelas:

```text
mart.match_results
mart.team_performance
mart.home_away_performance
mart.round_summary
mart.team_attack_defense
```

Aqui você responde perguntas como:

```text
Qual time fez mais pontos?
Qual time tem melhor saldo de gols?
Quais jogos terminaram empatados?
Qual time é melhor como mandante?
Qual time é melhor como visitante?
Qual rodada teve mais gols?
Qual time tem melhor ataque?
Qual time tem melhor defesa?
```

## Como Rodar

### 1. Subir o banco

```bash
docker compose up -d
```

### 2. Criar ambiente Python

No Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 3. Rodar com dados de exemplo

Este modo não precisa de token de API:

```bash
python src/extract_matches.py --sample
```

As partidas ficam identificadas com `source = 'sample'` e seguem normalmente
para os modelos de staging e mart.

### 4. Criar as camadas staging e mart

Depois de carregar os dados em `raw.matches`, execute os modelos e testes do dbt:

```powershell
.\.venv\Scripts\dbt.exe debug --project-dir dbt_futebol --profiles-dir dbt_futebol
.\.venv\Scripts\dbt.exe run --project-dir dbt_futebol --profiles-dir dbt_futebol
.\.venv\Scripts\dbt.exe test --project-dir dbt_futebol --profiles-dir dbt_futebol
```

### 5. Consultar o resultado

```bash
docker exec -it futebol-postgres psql -U futebol -d futebol_dw
```

Dentro do `psql`:

```sql
SELECT * FROM raw.matches;
SELECT * FROM staging.stg_matches;
SELECT * FROM mart.match_results;
SELECT * FROM mart.team_performance;
SELECT * FROM mart.home_away_performance;
SELECT * FROM mart.round_summary;
SELECT * FROM mart.team_attack_defense;
```

Também deixei exemplos prontos em:

```text
queries/example_queries.sql
```

## Rodar com a API real

Crie uma conta e token em:

```text
https://www.football-data.org/
```

Depois copie o exemplo de variáveis:

```bash
cp .env.example .env
```

No Windows PowerShell, se preferir:

```powershell
Copy-Item .env.example .env
```

Edite `.env` e preencha:

```text
FOOTBALL_DATA_API_TOKEN=seu_token
POSTGRES_PORT=5433
```

Depois rode:

```bash
python src/extract_matches.py --competition BSA --season 2025
```

## Rodar Transformações com dbt

Depois de carregar dados em `raw.matches`, rode:

```powershell
$env:POSTGRES_HOST='localhost'
$env:POSTGRES_PORT='5433'
$env:POSTGRES_DB='futebol_dw'
$env:POSTGRES_USER='futebol'
$env:POSTGRES_PASSWORD='futebol'

.\.venv\Scripts\dbt.exe debug --project-dir dbt_futebol --profiles-dir dbt_futebol
.\.venv\Scripts\dbt.exe run --project-dir dbt_futebol --profiles-dir dbt_futebol
.\.venv\Scripts\dbt.exe test --project-dir dbt_futebol --profiles-dir dbt_futebol
```

O `dbt run` cria:

```text
staging.stg_matches
mart.match_results
mart.team_performance
mart.home_away_performance
mart.round_summary
mart.team_attack_defense
```

O `dbt test` valida regras básicas de qualidade, como campos nulos,
unicidade e placares de jogos finalizados.

## Qualidade e testes

Instale as dependências de desenvolvimento:

```powershell
pip install -r requirements-dev.txt
```

Execute as verificações locais:

```powershell
ruff check src tests
ruff format --check src tests
pytest
.\.venv\Scripts\dbt.exe build --project-dir dbt_futebol --profiles-dir dbt_futebol
```

O workflow `.github/workflows/ci.yml` repete essas verificações em cada
`push` e `pull_request`. A integração sobe PostgreSQL, executa o sample duas
vezes, confirma que o upsert manteve quatro partidas e roda `dbt build`.

O extrator registra os headers de rate limit da API:

```text
X-RequestsAvailable
X-RequestCounter-Reset
```

Respostas HTTP `429`, `500`, `502`, `503` e `504` são tentadas novamente
com backoff. O header `Retry-After` é respeitado quando enviado pela API.

## Arquitetura

```text
src/extract_matches.py
  chama a API ou lê o arquivo sample
  insere cada partida em raw.matches

sql/01_schema.sql
  cria schemas e tabela raw

dbt_futebol/models/staging
  transforma JSON bruto em colunas limpas

dbt_futebol/models/marts
  cria tabelas analíticas
```

## Próximos Passos

1. Adicionar `Airflow` para agendar o pipeline.
2. Criar dashboard em Power BI, Metabase ou Streamlit.
3. Adicionar evolução da tabela por rodada.
4. Adicionar alertas para falhas e atrasos do pipeline.
