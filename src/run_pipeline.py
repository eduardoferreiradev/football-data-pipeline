"""Run extraction, validation, ingestion and dbt, with a local execution report."""

import argparse
import json
import os
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
from dotenv import load_dotenv

from src import extract_matches as extract
from src.migrate import apply_migrations
from src.publish import publish

ROOT = Path(__file__).resolve().parents[1]
PIPELINE_LOCK = 2026002


class PipelineBusyError(RuntimeError):
    pass


def coverage(data):
    matches = data["matches"]
    return {
        "matches": len(matches),
        "teams": len({m[s]["id"] for m in matches for s in ("homeTeam", "awayTeam")}),
        "rounds": len({m["matchday"] for m in matches}),
        "statuses": dict(Counter(m["status"] for m in matches)),
    }


def main(argv=None):
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--input", type=Path, help="Replay a saved API response.")
    group.add_argument("--sample", action="store_true")
    parser.add_argument("--execution-id", type=UUID, default=None)
    args = parser.parse_args(argv)
    extract.configure_logging()
    report = {
        "execution_id": str(args.execution_id or uuid4()),
        "started_at": datetime.now(UTC).isoformat(),
        "status": "running",
        "stage": "extract",
    }
    output = ROOT / "data" / "runs" / report["execution_id"]
    output.mkdir(parents=True)
    lock_connection = None
    try:
        competition = os.getenv("FOOTBALL_COMPETITION_CODE", "BSA")
        season = 2025 if args.sample else int(os.getenv("FOOTBALL_SEASON", "2026"))
        source = "sample" if args.sample else "football-data.org"
        report.update(source=source, competition=competition, season=season)
        if args.input or args.sample:
            data = json.loads(
                (args.input or extract.DEFAULT_SAMPLE_PATH).read_text(encoding="utf-8")
            )
        else:
            token = os.getenv("FOOTBALL_DATA_API_TOKEN")
            if not token:
                raise extract.ConfigurationError("API token required.")
            data = extract.load_matches_from_api(competition, season, token)
        (output / "response.json").write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )

        report["observed_at"] = datetime.now(UTC).isoformat()
        if args.input:
            previous = json.loads(
                args.input.with_name("report.json").read_text(encoding="utf-8")
            )
            report["observed_at"] = previous["observed_at"]
        observed_at = datetime.fromisoformat(report["observed_at"])
        if observed_at.tzinfo is None:
            raise extract.PayloadValidationError("Replay timestamp requires timezone.")
        report["stage"] = "validate"
        extract.validate_matches_payload(data, competition, season)
        report["coverage"] = coverage(data)
        if not args.sample and competition == "BSA":
            counts = tuple(
                report["coverage"][k] for k in ("matches", "teams", "rounds")
            )
            if counts != (380, 20, 38):
                incoming_ids = {m["id"] for m in data["matches"]}
                try:
                    with extract.connect_to_postgres() as conn:
                        known = {
                            row[0]
                            for row in conn.execute(
                                "SELECT match_id FROM raw.matches "
                                "WHERE source=%s AND competition_code=%s "
                                "AND season_year=%s",
                                (source, competition, season),
                            ).fetchall()
                        }
                except psycopg.errors.UndefinedTable:
                    known = set()
                report["coverage"]["missing_match_ids"] = sorted(known - incoming_ids)
                report["coverage"]["new_match_ids"] = sorted(incoming_ids - known)
                raise extract.PayloadValidationError("Incomplete BSA season calendar.")
        report["stage"] = "lock"
        lock_connection = extract.connect_to_postgres()
        lock_connection.autocommit = True
        acquired = lock_connection.execute(
            "SELECT pg_try_advisory_lock(%s)", (PIPELINE_LOCK,)
        ).fetchone()[0]
        if not acquired:
            raise PipelineBusyError("Another pipeline is running.")
        report["stage"] = "schema"
        with extract.connect_to_postgres() as conn:
            report["migrations_applied"] = apply_migrations(conn, ROOT)
        report["stage"] = "ingest"
        extract.upsert_raw_matches(
            data,
            competition,
            season,
            source,
            observed_at=observed_at,
            run_id=UUID(report["execution_id"]),
        )
        report["stage"] = "dbt"
        dbt_executable = Path(sys.executable).parent / (
            "dbt.exe" if os.name == "nt" else "dbt"
        )
        artifacts = output / "dbt"
        namespace = "build_" + UUID(report["execution_id"]).hex
        subprocess.run(
            [
                str(dbt_executable),
                "build",
                "--project-dir",
                str(ROOT / "dbt_futebol"),
                "--profiles-dir",
                str(ROOT / "dbt_futebol"),
                "--target-path",
                str(artifacts),
                "--log-path",
                str(output / "dbt_logs"),
                "--vars",
                json.dumps({"build_namespace": namespace}),
            ],
            check=True,
            timeout=int(os.getenv("DBT_TIMEOUT_SECONDS", "1800")),
        )
        report["stage"] = "publish"
        with extract.connect_to_postgres() as conn:
            report["published_models"] = publish(
                conn, artifacts, UUID(report["execution_id"])
            )
        with extract.connect_to_postgres() as conn:
            fields = (
                "baseline_matches",
                "added_matches",
                "missing_matches",
                "updated_matches",
                "field_change_count",
                "is_latest_observation",
            )
            row = conn.execute(
                "SELECT "
                + ", ".join(fields)
                + " FROM mart.collection_changes_summary WHERE run_id=%s",
                (UUID(report["execution_id"]),),
            ).fetchone()
            report["changes"] = dict(zip(fields, row, strict=True))
        report["status"] = "succeeded"
    except Exception as exc:
        report["status"] = "skipped" if isinstance(exc, PipelineBusyError) else "failed"
        report["error_type"] = type(exc).__name__
        report["retryable"] = isinstance(
            exc,
            (
                PipelineBusyError,
                extract.ApiRequestError,
                psycopg.OperationalError,
                subprocess.CalledProcessError,
                subprocess.TimeoutExpired,
                OSError,
            ),
        )
    finally:
        if lock_connection is not None:
            lock_connection.close()
        report["finished_at"] = datetime.now(UTC).isoformat()
        (output / "report.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
        print(json.dumps(report, indent=2))
    return (
        0
        if report["status"] == "succeeded"
        else (2 if report["status"] == "skipped" else 1)
    )


if __name__ == "__main__":
    raise SystemExit(main())
