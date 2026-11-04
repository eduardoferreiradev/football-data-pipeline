"""Compare manually defined events against dbt results in PostgreSQL."""

import json
import os
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg
import pytest

from src import extract_matches as extract
from src.history import ingest


def test_observation_changes_presence_replay_and_isolation(database, build_dbt):
    template = json.loads(extract.DEFAULT_SAMPLE_PATH.read_text(encoding="utf-8"))
    template["matches"] = template["matches"][:2]
    template["matches"][0]["status"] = "TIMED"
    template["matches"][0]["score"]["fullTime"] = {"home": None, "away": None}
    source = "changes-" + uuid4().hex
    start = datetime.now(UTC)
    run_ids = [uuid4() for _ in range(7)]

    def load(data, index):
        ingest(
            data,
            "BSA",
            2025,
            source,
            database,
            start + timedelta(minutes=index),
            run_ids[index],
        )

    load(template, 0)
    corrected = deepcopy(template)
    m = corrected["matches"][0]
    m.update(status="FINISHED", utcDate="2025-12-01T20:00:00Z", matchday=2)
    m["score"]["fullTime"] = {"home": 2, "away": 1}
    load(corrected, 1)
    metadata = deepcopy(corrected)
    metadata["matches"][0]["lastUpdated"] = "2025-12-02T20:00:00Z"
    metadata["matches"][1]["homeTeam"]["name"] = "Nome atualizado"
    load(metadata, 2)
    missing = deepcopy(metadata)
    missing["matches"] = missing["matches"][1:]
    load(missing, 3)
    load(metadata, 4)
    other_source = "other-" + uuid4().hex
    ingest(template, "BSA", 2025, other_source, database, start)
    broken = deepcopy(metadata)
    broken["matches"].append(broken["matches"][0])
    with pytest.raises(psycopg.errors.UniqueViolation):
        load(broken, 5)

    with database() as conn:
        assert conn.execute(
            "SELECT count(*) FROM raw.matches WHERE source=%s", (source,)
        ).fetchone() == (2,)

    # An old replay arrives late; chronology must not show a reversal at the end.
    ingest(
        template,
        "BSA",
        2025,
        source,
        database,
        start - timedelta(minutes=1),
        run_ids[6],
    )
    build_dbt(os.environ["FOOTBALL_TEST_DSN"])
    with database() as conn:
        rows = conn.execute(
            "SELECT field_name, previous_value, current_value FROM mart.match_changes "
            "WHERE run_id=%s ORDER BY field_name",
            (run_ids[1],),
        ).fetchall()
        assert {r[0] for r in rows} == {
            "status",
            "scheduled_at",
            "round",
            "home_score",
            "away_score",
        }
        fields = {r[0]: r[1:] for r in rows}
        assert fields["status"] == ("TIMED", "FINISHED")
        assert fields["home_score"] == (None, 2)
        assert fields["away_score"] == (None, 1)
        for index in (0, 2, 5):
            assert conn.execute(
                "SELECT count(*) FROM mart.match_changes WHERE run_id=%s",
                (run_ids[index],),
            ).fetchone() == (0,)
        for index, kind in [(3, "missing"), (4, "added"), (6, "baseline")]:
            rows = conn.execute(
                "SELECT change_type, field_name FROM mart.match_changes "
                "WHERE run_id=%s",
                (run_ids[index],),
            ).fetchall()
            assert rows == [(kind, "presence")] * (2 if index == 6 else 1)
        assert conn.execute(
            "SELECT updated_matches, field_change_count FROM "
            "mart.collection_changes_summary WHERE run_id=%s",
            (run_ids[1],),
        ).fetchone() == (1, 5)
        assert conn.execute(
            "SELECT baseline_matches, added_matches, missing_matches, "
            "updated_matches, field_change_count FROM mart.collection_changes_summary "
            "WHERE run_id=%s",
            (run_ids[2],),
        ).fetchone() == (0, 0, 0, 0, 0)
        assert conn.execute(
            "SELECT count(*) FROM mart.match_changes WHERE source=%s "
            "AND change_type='baseline'",
            (other_source,),
        ).fetchone() == (2,)


def test_incomplete_response_reports_missing_ids_without_ingesting(
    database, monkeypatch, tmp_path
):
    from src import run_pipeline

    data = json.loads(extract.DEFAULT_SAMPLE_PATH.read_text(encoding="utf-8"))
    ingest(data, "BSA", 2025, "football-data.org", database)
    missing_id = data["matches"].pop()["id"]
    folder = tmp_path / "input"
    folder.mkdir()
    payload_path = folder / "response.json"
    payload_path.write_text(json.dumps(data), encoding="utf-8")
    (folder / "report.json").write_text(
        json.dumps({"observed_at": datetime.now(UTC).isoformat()}), encoding="utf-8"
    )
    monkeypatch.setattr(run_pipeline, "ROOT", tmp_path)
    monkeypatch.setattr(run_pipeline, "load_dotenv", lambda *args: None)
    monkeypatch.setattr(extract, "connect_to_postgres", database)
    monkeypatch.setenv("FOOTBALL_SEASON", "2025")
    monkeypatch.setenv("FOOTBALL_COMPETITION_CODE", "BSA")
    assert run_pipeline.main(["--input", str(payload_path)]) == 1
    reports = list((tmp_path / "data/runs").glob("*/report.json"))
    report = json.loads(reports[0].read_text(encoding="utf-8"))
    assert report["status"] == "failed" and report["stage"] == "validate"
    assert report["coverage"]["missing_match_ids"] == [missing_id]
    with database() as conn:
        assert conn.execute(
            "SELECT count(*) FROM raw.matches WHERE source='football-data.org'"
        ).fetchone() == (4,)
        assert conn.execute(
            "SELECT count(*) FROM ops.runs WHERE source='football-data.org'"
        ).fetchone() == (1,)
