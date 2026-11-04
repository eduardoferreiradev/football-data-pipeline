import json
import shutil
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

from src import extract_matches as extract
from src import run_pipeline
from src.migrate import apply_migrations
from src.publish import PublicationError, publish, rollback, validated_models

ROOT = Path(__file__).resolve().parents[1]


def artifacts(folder, run_id, database_name):
    folder.mkdir(parents=True, exist_ok=True)
    nodes = {}
    for name in ("publication_a", "publication_b"):
        nodes["model.test." + name] = {
            "resource_type": "model",
            "alias": name,
            "database": database_name,
            "schema": "build_" + run_id.hex + "_mart",
            "config": {"schema": "mart", "materialized": "table", "enabled": True},
        }
    nodes["test.test.quality"] = {"resource_type": "test", "config": {"enabled": True}}
    manifest = {"metadata": {"invocation_id": "invocation"}, "nodes": nodes}
    results = {
        "metadata": {"invocation_id": "invocation"},
        "results": [
            {
                "unique_id": key,
                "status": "pass" if key.startswith("test.") else "success",
            }
            for key in nodes
        ],
    }
    (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (folder / "run_results.json").write_text(json.dumps(results), encoding="utf-8")
    return manifest, results


@pytest.mark.parametrize("problem", ["failed", "warning", "incomplete", "invocation"])
def test_rejects_invalid_artifacts(tmp_path, problem):
    run_id = uuid4()
    _, results = artifacts(tmp_path, run_id, "test")
    if problem == "incomplete":
        results["results"].pop()
    elif problem == "invocation":
        results["metadata"]["invocation_id"] = "another"
    else:
        results["results"][-1]["status"] = "fail" if problem == "failed" else "warn"
    (tmp_path / "run_results.json").write_text(json.dumps(results), encoding="utf-8")
    with pytest.raises(PublicationError):
        validated_models(tmp_path, run_id)


def test_transactional_activation_and_rollback(fresh_database, tmp_path):
    with psycopg.connect(fresh_database) as conn:
        apply_migrations(conn)
        for name in ("publication_a", "publication_b"):
            conn.execute(
                sql.SQL("CREATE TABLE mart.{} AS SELECT 0::INT AS value").format(
                    sql.Identifier(name)
                )
            )

    def generation(value, invalid=False):
        run_id = uuid4()
        folder = tmp_path / run_id.hex
        with psycopg.connect(fresh_database) as conn:
            name = conn.execute("SELECT current_database()").fetchone()[0]
            schema = "build_" + run_id.hex + "_mart"
            conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
            for table in ("publication_a", "publication_b"):
                expression = (
                    "'bad'::TEXT" if invalid and table.endswith("_b") else str(value)
                )
                conn.execute(
                    sql.SQL("CREATE TABLE {}.{} AS SELECT {} AS value").format(
                        sql.Identifier(schema),
                        sql.Identifier(table),
                        sql.SQL(expression),
                    )
                )
        artifacts(folder, run_id, name)
        return run_id, folder

    first, folder = generation(1)
    with psycopg.connect(fresh_database) as conn:
        assert publish(conn, folder, first) == 2
        conn.execute(
            "CREATE VIEW mart.publication_consumer AS "
            "SELECT value FROM mart.publication_a UNION ALL "
            "SELECT value FROM mart.publication_b"
        )
    bad, folder = generation(2, invalid=True)
    with psycopg.connect(fresh_database) as conn:
        with pytest.raises(psycopg.errors.InvalidTableDefinition):
            publish(conn, folder, bad)
        assert conn.execute(
            "SELECT value FROM mart.publication_consumer"
        ).fetchall() == [(1,), (1,)]
        assert conn.execute(
            "SELECT count(*) FROM ops.publications WHERE run_id=%s", (bad,)
        ).fetchone() == (0,)
    second, folder = generation(2)
    with psycopg.connect(fresh_database) as conn:
        publish(conn, folder, second)
        assert conn.execute(
            "SELECT value FROM mart.publication_consumer"
        ).fetchall() == [(2,), (2,)]
        rollback(conn, first)
        assert conn.execute(
            "SELECT value FROM mart.publication_consumer"
        ).fetchall() == [(1,), (1,)]
        assert conn.execute(
            "SELECT run_id FROM ops.current_publication"
        ).fetchone() == (first,)


def test_real_dbt_failure_preserves_publication_and_recovers(
    fresh_database, monkeypatch, tmp_path
):
    for directory in ("sql", "dbt_futebol"):
        shutil.copytree(
            ROOT / directory,
            tmp_path / directory,
            ignore=shutil.ignore_patterns("target", "logs", "dbt_packages"),
        )
    settings = conninfo_to_dict(fresh_database)
    for env_key, key in {
        "POSTGRES_HOST": "host",
        "POSTGRES_PORT": "port",
        "POSTGRES_DB": "dbname",
        "POSTGRES_USER": "user",
        "POSTGRES_PASSWORD": "password",
    }.items():
        monkeypatch.setenv(env_key, settings.get(key, ""))
    monkeypatch.setenv("DBT_SEND_ANONYMOUS_USAGE_STATS", "false")
    monkeypatch.setattr(run_pipeline, "ROOT", tmp_path)
    monkeypatch.setattr(run_pipeline, "load_dotenv", lambda *args: None)
    monkeypatch.setattr(
        extract, "connect_to_postgres", lambda: psycopg.connect(fresh_database)
    )
    data = json.loads(extract.DEFAULT_SAMPLE_PATH.read_text(encoding="utf-8"))
    sample = tmp_path / "sample.json"
    sample.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(extract, "DEFAULT_SAMPLE_PATH", sample)
    first = uuid4()
    assert run_pipeline.main(["--sample", "--execution-id", str(first)]) == 0
    original = data["matches"][0]["score"]["fullTime"]["home"]
    changed = deepcopy(data)
    changed["matches"][0]["score"]["fullTime"]["home"] = original + 5
    sample.write_text(json.dumps(changed), encoding="utf-8")
    fail_test = tmp_path / "dbt_futebol/tests/assert_deliberate_failure.sql"
    fail_test.write_text("SELECT 1 AS deliberate_failure", encoding="utf-8")
    rejected = uuid4()
    assert run_pipeline.main(["--sample", "--execution-id", str(rejected)]) == 1
    with psycopg.connect(fresh_database) as conn:
        assert conn.execute(
            "SELECT run_id FROM ops.current_publication"
        ).fetchone() == (first,)
        assert conn.execute(
            "SELECT home_score FROM mart.match_results WHERE match_id=%s",
            (data["matches"][0]["id"],),
        ).fetchone() == (original,)
        assert conn.execute(
            "SELECT (payload #>> '{score,fullTime,home}')::INT FROM raw.matches "
            "WHERE source='sample' AND match_id=%s",
            (data["matches"][0]["id"],),
        ).fetchone() == (original + 5,)
    report = json.loads(
        (tmp_path / "data/runs" / str(rejected) / "report.json").read_text(
            encoding="utf-8"
        )
    )
    assert report["status"] == "failed" and report["stage"] == "dbt"
    fail_test.unlink()
    recovered = uuid4()
    assert run_pipeline.main(["--sample", "--execution-id", str(recovered)]) == 0
    with psycopg.connect(fresh_database) as conn:
        assert conn.execute(
            "SELECT home_score FROM mart.match_results WHERE match_id=%s",
            (data["matches"][0]["id"],),
        ).fetchone() == (original + 5,)
        rollback(conn, first)
        assert conn.execute(
            "SELECT home_score FROM mart.match_results WHERE match_id=%s",
            (data["matches"][0]["id"],),
        ).fetchone() == (original,)
