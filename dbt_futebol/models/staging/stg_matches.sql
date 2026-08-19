SELECT
    source,
    match_id,
    competition_code,
    season_year,
    extracted_at,
    (payload ->> 'utcDate')::TIMESTAMPTZ AS match_datetime_utc,
    payload ->> 'status' AS status,
    NULLIF(payload ->> 'matchday', '')::INTEGER AS matchday,
    payload ->> 'stage' AS stage,
    NULLIF(payload #>> '{homeTeam,id}', '')::BIGINT AS home_team_id,
    payload #>> '{homeTeam,name}' AS home_team_name,
    NULLIF(payload #>> '{awayTeam,id}', '')::BIGINT AS away_team_id,
    payload #>> '{awayTeam,name}' AS away_team_name,
    NULLIF(payload #>> '{score,fullTime,home}', '')::INTEGER AS home_score,
    NULLIF(payload #>> '{score,fullTime,away}', '')::INTEGER AS away_score,
    payload #>> '{score,winner}' AS winner
FROM {{ source('raw', 'matches') }}
WHERE source = 'football-data.org'
