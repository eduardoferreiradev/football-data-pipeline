import json
import shutil
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from src import extract_matches as extract
from src.history import ingest
from src.migrate import MigrationError, apply_migrations

ROOT = Path(__file__).resolve().parents[1]


def test_adopts_legacy_database_and_preserves_observations(fresh_database):
    def connect():
        return psycopg.connect(fresh_database)

    with connect() as conn:
        for name in ("01_schema.sql", "02_history.sql"):
            conn.execute((ROOT / "sql" / name).read_text(encoding="utf-8"))
    data = json.loads(extract.DEFAULT_SAMPLE_PATH.read_text(encoding="utf-8"))
    source = "migration-" + uuid4().hex
    ingest(data, "BSA", 2025, source, connect)
    with connect() as conn:
        assert len(apply_migrations(conn)) == 3
        assert apply_migrations(conn) == []
        assert conn.execute("SELECT count(*) FROM raw.matches").fetchone() == (4,)
        assert conn.execute("SELECT count(*) FROM raw.observations").fetchone() == (4,)
        assert conn.execute("SELECT count(*) FROM ops.runs").fetchone() == (1,)


def test_rejects_changed_or_missing_migration(database, tmp_path):
    shutil.copytree(ROOT / "sql", tmp_path / "sql")
    changed = tmp_path / "sql/01_schema.sql"
    changed.write_text(
        changed.read_text(encoding="utf-8") + "\n-- altered\n", encoding="utf-8"
    )
    with database() as conn, pytest.raises(MigrationError, match="changed"):
        apply_migrations(conn, tmp_path)
    shutil.copyfile(ROOT / "sql/01_schema.sql", changed)
    (tmp_path / "sql/migrations/003_publications.sql").unlink()
    with database() as conn, pytest.raises(MigrationError, match="missing"):
        apply_migrations(conn, tmp_path)


def test_failed_script_rolls_back_schema_and_registry(database, tmp_path):
    shutil.copytree(ROOT / "sql", tmp_path / "sql")
    (tmp_path / "sql/migrations/004_failure.sql").write_text(
        "CREATE TABLE ops.migration_rollback_probe(id INT); "
        "SELECT * FROM ops.deliberately_missing_table;",
        encoding="utf-8",
    )
    with database() as conn, pytest.raises(psycopg.errors.UndefinedTable):
        apply_migrations(conn, tmp_path)
    with database() as conn:
        assert conn.execute(
            "SELECT to_regclass('ops.migration_rollback_probe')"
        ).fetchone() == (None,)
        assert conn.execute(
            "SELECT count(*) FROM ops.schema_migrations WHERE version LIKE '%004%'"
        ).fetchone() == (0,)
