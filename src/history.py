"""Observations and latest state are committed together."""

import json
from datetime import UTC, datetime
from uuid import uuid4

from psycopg.types.json import Jsonb


def ingest(data, competition, season, source, connect, observed_at=None, run_id=None):
    run_id = run_id or uuid4()
    observed = observed_at or datetime.now(UTC)
    with connect() as conn:
        conn.execute(
            "INSERT INTO ops.runs (run_id,source,competition_code,season_year,"
            "observed_at,status) VALUES (%s,%s,%s,%s,%s,'running')",
            (run_id, source, competition, season, observed),
        )
    try:
        with connect() as conn:
            conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                (json.dumps([source, competition, season]),),
            )
            changed = 0
            for m in data["matches"]:
                old = conn.execute(
                    "SELECT payload, extracted_at FROM raw.matches "
                    "WHERE source=%s AND match_id=%s",
                    (source, m["id"]),
                ).fetchone()
                changed += old is None or (old[0] != m and observed >= old[1])
                conn.execute(
                    "INSERT INTO raw.observations VALUES (%s,%s,%s,%s)",
                    (run_id, source, m["id"], Jsonb(m)),
                )
                conn.execute(
                    """
                    INSERT INTO raw.matches
                      (source,competition_code,season_year,match_id,extracted_at,payload)
                    VALUES (%s,%s,%s,%s,%s,%s)
                    ON CONFLICT(source,match_id) DO UPDATE SET
                      competition_code=EXCLUDED.competition_code,
                      season_year=EXCLUDED.season_year,
                      extracted_at=EXCLUDED.extracted_at,payload=EXCLUDED.payload
                    WHERE EXCLUDED.extracted_at >= raw.matches.extracted_at
                """,
                    (source, competition, season, m["id"], observed, Jsonb(m)),
                )
            conn.execute(
                """
                UPDATE ops.runs SET status='succeeded',finished_at=clock_timestamp(),
                match_count=%s,changed_count=%s WHERE run_id=%s
            """,
                (len(data["matches"]), changed, run_id),
            )
    except Exception as exc:
        with connect() as conn:
            conn.execute(
                "UPDATE ops.runs SET status='failed',"
                "finished_at=clock_timestamp(),error_type=%s WHERE run_id=%s",
                (type(exc).__name__, run_id),
            )
        raise
    return len(data["matches"])
