import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from src.migrate import apply_migrations


@pytest.fixture
def build_dbt(tmp_path):
    def build(database_dsn):
        settings = conninfo_to_dict(database_dsn)
        env = os.environ.copy()
        for key, setting in {
            "POSTGRES_HOST": "host",
            "POSTGRES_PORT": "port",
            "POSTGRES_DB": "dbname",
            "POSTGRES_USER": "user",
            "POSTGRES_PASSWORD": "password",
        }.items():
            env[key] = settings.get(setting, "")
        env["DBT_SEND_ANONYMOUS_USAGE_STATS"] = "false"
        root = Path(__file__).resolve().parents[1]
        executable = Path(sys.executable).parent / (
            "dbt.exe" if os.name == "nt" else "dbt"
        )
        result = subprocess.run(
            [
                str(executable),
                "build",
                "--project-dir",
                str(root / "dbt_futebol"),
                "--profiles-dir",
                str(root / "dbt_futebol"),
                "--target-path",
                str(tmp_path / "target"),
                "--log-path",
                str(tmp_path / "logs"),
            ],
            env=env,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    return build


@pytest.fixture
def database():
    dsn = os.getenv("FOOTBALL_TEST_DSN")
    if not dsn:
        pytest.skip("FOOTBALL_TEST_DSN is required for PostgreSQL integration.")

    def connect():
        return psycopg.connect(dsn)

    root = Path(__file__).resolve().parents[1]
    with connect() as conn:
        apply_migrations(conn, root)
    return connect


@pytest.fixture
def fresh_database():
    dsn = os.getenv("FOOTBALL_TEST_DSN")
    if not dsn:
        pytest.skip("FOOTBALL_TEST_DSN is required for PostgreSQL integration.")
    name = "football_test_" + uuid4().hex
    with psycopg.connect(
        make_conninfo(dsn, dbname="postgres"), autocommit=True, connect_timeout=10
    ) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            yield make_conninfo(dsn, dbname=name)
        finally:
            admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))
