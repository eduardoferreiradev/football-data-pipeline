import json

from src import extract_matches as extract
from src import run_pipeline


def test_concurrent_pipeline_is_skipped_and_lock_is_released(
    database, monkeypatch, tmp_path
):
    monkeypatch.setattr(run_pipeline, "ROOT", tmp_path)
    monkeypatch.setattr(run_pipeline, "load_dotenv", lambda *a: None)
    monkeypatch.setattr(extract, "connect_to_postgres", database)
    with database() as conn:
        before = conn.execute("SELECT count(*) FROM ops.runs").fetchone()[0]
    with database() as owner:
        owner.execute("SELECT pg_advisory_lock(%s)", (run_pipeline.PIPELINE_LOCK,))
        assert run_pipeline.main(["--sample"]) == 2
    report = json.loads(
        next((tmp_path / "data/runs").glob("*/report.json")).read_text(encoding="utf-8")
    )
    assert report["status"] == "skipped"
    assert report["stage"] == "lock"
    assert report["retryable"] is True
    with database() as conn:
        assert conn.execute(
            "SELECT pg_try_advisory_lock(%s)", (run_pipeline.PIPELINE_LOCK,)
        ).fetchone() == (True,)
        assert conn.execute("SELECT count(*) FROM ops.runs").fetchone() == (before,)
