"""Integration checks use only the explicit, isolated test database."""

import json
from datetime import UTC, datetime, timedelta

import psycopg
import pytest

from src import extract_matches as extract
from src.history import ingest


def test_repetition_correction_old_replay_and_rollback(database):
    data = json.loads(extract.DEFAULT_SAMPLE_PATH.read_text(encoding="utf-8"))
    data["matches"] = data["matches"][:1]
    source = "test-history-" + str(datetime.now(UTC).timestamp())
    now = datetime.now(UTC)
    ingest(data, "BSA", 2025, source, database, now)
    ingest(data, "BSA", 2025, source, database, now)
    data["matches"][0]["score"]["fullTime"]["home"] = 7
    ingest(data, "BSA", 2025, source, database, now + timedelta(seconds=1))
    data["matches"][0]["score"]["fullTime"]["home"] = 0
    ingest(data, "BSA", 2025, source, database, now)
    with database() as conn:
        assert (
            conn.execute(
                "SELECT count(*) FROM raw.matches WHERE source=%s", (source,)
            ).fetchone()[0]
            == 1
        )
        assert (
            conn.execute(
                "SELECT count(*) FROM raw.observations WHERE source=%s", (source,)
            ).fetchone()[0]
            == 4
        )
        assert (
            conn.execute(
                "SELECT payload #>> '{score,fullTime,home}' "
                "FROM raw.matches WHERE source=%s",
                (source,),
            ).fetchone()[0]
            == "7"
        )
    # A duplicate in the internal ingest call forces a constraint failure mid-batch.
    data["matches"].append(data["matches"][0])
    with pytest.raises(psycopg.errors.UniqueViolation):
        ingest(data, "BSA", 2025, source, database, now + timedelta(seconds=2))
    with database() as conn:
        assert (
            conn.execute(
                "SELECT count(*) FROM raw.observations WHERE source=%s", (source,)
            ).fetchone()[0]
            == 4
        )
        assert (
            conn.execute(
                "SELECT count(*) FROM ops.runs WHERE source=%s AND status='failed'",
                (source,),
            ).fetchone()[0]
            == 1
        )
