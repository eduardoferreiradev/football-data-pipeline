"""Transactional migration registry for new and already initialized databases."""

import hashlib

from dotenv import load_dotenv

from src.extract_matches import PROJECT_ROOT, connect_to_postgres


class MigrationError(RuntimeError):
    pass


def apply_migrations(connection, root=PROJECT_ROOT):
    paths = [root / "sql/01_schema.sql", root / "sql/02_history.sql"]
    paths += sorted((root / "sql/migrations").glob("*.sql"))
    applied = []
    with connection.transaction():
        connection.execute("SELECT pg_advisory_xact_lock(2026001)")
        connection.execute("CREATE SCHEMA IF NOT EXISTS ops")
        connection.execute("""
            CREATE TABLE IF NOT EXISTS ops.schema_migrations (
                version TEXT PRIMARY KEY, checksum TEXT NOT NULL,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
            )
        """)
        versions = {p.relative_to(root).as_posix() for p in paths}
        stored = dict(
            connection.execute(
                "SELECT version,checksum FROM ops.schema_migrations"
            ).fetchall()
        )
        if set(stored) - versions:
            raise MigrationError("An applied migration is missing from this checkout.")
        for path in paths:
            text = path.read_text(encoding="utf-8")
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
            version = path.relative_to(root).as_posix()
            if version in stored:
                if stored[version] != digest:
                    raise MigrationError(f"Applied migration changed: {version}")
                continue
            connection.execute(text)
            connection.execute(
                "INSERT INTO ops.schema_migrations(version,checksum) VALUES (%s,%s)",
                (version, digest),
            )
            applied.append(version)
    return applied


def main():
    load_dotenv(PROJECT_ROOT / ".env")
    with connect_to_postgres() as conn:
        applied = apply_migrations(conn)
    print(f"Applied {len(applied)} migrations.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
