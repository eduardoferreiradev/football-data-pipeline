"""Publish validated dbt generations through stable views in one transaction."""

import argparse
import json
from uuid import UUID

from dotenv import load_dotenv
from psycopg import sql
from psycopg.types.json import Jsonb

from src.extract_matches import PROJECT_ROOT, connect_to_postgres

SCHEMAS = {"staging", "intermediate", "mart"}


class PublicationError(RuntimeError):
    pass


def validated_models(artifacts, run_id):
    manifest = json.loads((artifacts / "manifest.json").read_text(encoding="utf-8"))
    results = json.loads((artifacts / "run_results.json").read_text(encoding="utf-8"))
    if manifest["metadata"]["invocation_id"] != results["metadata"]["invocation_id"]:
        raise PublicationError("Artifacts belong to different invocations.")
    prefix = "build_" + UUID(str(run_id)).hex
    nodes = {
        key: node
        for key, node in manifest["nodes"].items()
        if node["resource_type"] in ("model", "test")
        and node.get("config", {}).get("enabled", True)
    }
    observed = {r["unique_id"]: r for r in results["results"]}
    if not nodes or set(observed) != set(nodes):
        raise PublicationError("The full model and test set must be executed.")
    models = []
    for key, node in nodes.items():
        expected_status = "success" if node["resource_type"] == "model" else "pass"
        if observed[key]["status"] != expected_status:
            raise PublicationError(
                "Only successful builds and passing tests can publish."
            )
        if node["resource_type"] != "model":
            continue
        public_schema = node["config"].get("schema")
        if (
            public_schema not in SCHEMAS
            or node["schema"] != prefix + "_" + public_schema
        ):
            raise PublicationError("Build must use the isolated execution schemas.")
        if node["config"].get("materialized") not in ("table", "view"):
            raise PublicationError("Unsupported model materialization.")
        models.append(
            {
                "schema": public_schema,
                "name": node["alias"],
                "build_schema": node["schema"],
                "database": node["database"],
            }
        )
    if not models or len({(m["schema"], m["name"]) for m in models}) != len(models):
        raise PublicationError("Invalid model set.")
    return models


def _activate(connection, run_id, models):
    connection.execute("SELECT pg_advisory_xact_lock(2026003)")
    connection.execute("SET LOCAL lock_timeout = '10s'")
    connection.execute("SET LOCAL statement_timeout = '60s'")
    current_database = connection.execute("SELECT current_database()").fetchone()[0]
    previous = connection.execute(
        "SELECT p.models FROM ops.current_publication c "
        "JOIN ops.publications p USING(run_id) WHERE c.singleton"
    ).fetchone()
    if previous and {(m["schema"], m["name"]) for m in previous[0]} != {
        (m["schema"], m["name"]) for m in models
    }:
        raise PublicationError("Changing the model set requires a contract migration.")

    for model in sorted(models, key=lambda m: (m["schema"], m["name"])):
        schema, name = model["schema"], model["name"]
        if schema not in SCHEMAS or model["database"] != current_database:
            raise PublicationError(
                "Publication points outside the configured database."
            )
        connection.execute(
            sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema))
        )
        existing = connection.execute(
            """
            SELECT c.relkind FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname=%s AND c.relname=%s
        """,
            (schema, name),
        ).fetchone()
        if existing and existing[0] != "v":
            if existing[0] != "r":
                raise PublicationError("Unexpected public relation type.")
            legacy = "legacy_" + UUID(str(run_id)).hex + "_" + schema
            connection.execute(
                sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(legacy))
            )
            connection.execute(
                sql.SQL("ALTER TABLE {}.{} SET SCHEMA {}").format(
                    sql.Identifier(schema), sql.Identifier(name), sql.Identifier(legacy)
                )
            )
        connection.execute(
            sql.SQL("CREATE OR REPLACE VIEW {}.{} AS SELECT * FROM {}.{}").format(
                sql.Identifier(schema),
                sql.Identifier(name),
                sql.Identifier(model["build_schema"]),
                sql.Identifier(name),
            )
        )
    connection.execute(
        """
        INSERT INTO ops.current_publication(singleton,run_id) VALUES (TRUE,%s)
        ON CONFLICT(singleton) DO UPDATE SET run_id=EXCLUDED.run_id,
            activated_at=clock_timestamp()
    """,
        (run_id,),
    )
    connection.execute(
        "INSERT INTO ops.publication_events(run_id) VALUES (%s)", (run_id,)
    )


def publish(connection, artifacts, run_id):
    models = validated_models(artifacts, run_id)
    with connection.transaction():
        connection.execute(
            "INSERT INTO ops.publications(run_id,models) VALUES (%s,%s)",
            (run_id, Jsonb(models)),
        )
        _activate(connection, run_id, models)
    return len(models)


def rollback(connection, run_id):
    with connection.transaction():
        row = connection.execute(
            "SELECT models FROM ops.publications WHERE run_id=%s", (run_id,)
        ).fetchone()
        if row is None:
            raise PublicationError("Unknown publication.")
        _activate(connection, run_id, row[0])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rollback", type=UUID, required=True)
    args = parser.parse_args()
    load_dotenv(PROJECT_ROOT / ".env")
    with connect_to_postgres() as guard:
        guard.autocommit = True
        if not guard.execute("SELECT pg_try_advisory_lock(2026002)").fetchone()[0]:
            raise PublicationError("Pipeline is active; retry rollback later.")
        with connect_to_postgres() as connection:
            rollback(connection, args.rollback)
    print(f"Activated publication {args.rollback}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
