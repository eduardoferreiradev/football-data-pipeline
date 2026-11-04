"""Clock-controlled operational behavior; no sleeps or real external calls."""

import json
from datetime import UTC, datetime, timedelta
from subprocess import CompletedProcess

import pytest

from src import scheduler as module
from src.scheduler import AlreadyRunning, Outcome, Scheduler, Settings, instance_lock


def moment(value="2026-10-31T10:00:00+00:00"):
    return datetime.fromisoformat(value)


def test_brasilia_due_slot_before_and_at_six():
    settings = Settings()
    assert settings.latest_slot(moment("2026-10-31T08:59:00+00:00")).isoformat() == (
        "2026-10-30T06:00:00-03:00"
    )
    assert settings.latest_slot(moment("2026-10-31T09:00:00+00:00")).isoformat() == (
        "2026-10-31T06:00:00-03:00"
    )


def test_daily_success_survives_restart_and_catches_latest_missed_day(tmp_path):
    now = [moment()]
    executions = []

    def execute(execution_id):
        executions.append(execution_id)
        return Outcome("succeeded")

    settings = Settings()
    scheduler = Scheduler(tmp_path, settings, execute, lambda: now[0])
    assert scheduler.tick(now[0])
    restarted = Scheduler(tmp_path, settings, execute, lambda: now[0])
    assert not restarted.tick(now[0] + timedelta(hours=1))
    # A backwards clock must not repeat yesterday's slot.
    assert not restarted.tick(now[0] - timedelta(hours=5))
    now[0] += timedelta(days=4)
    assert restarted.tick(now[0])
    assert len(executions) == 2
    assert restarted.read()["attempts"] == 1
    assert restarted.read()["scheduled_for"] == "2026-11-04T06:00:00-03:00"


def test_retry_wait_then_success(tmp_path):
    now = [moment()]
    outcomes = iter([Outcome("failed", True, "OperationalError"), Outcome("succeeded")])
    scheduler = Scheduler(
        tmp_path, Settings(), lambda _: next(outcomes), lambda: now[0]
    )
    assert scheduler.tick(now[0])
    assert scheduler.read()["status"] == "retry_wait"
    assert not scheduler.read()["needs_attention"]
    now[0] += timedelta(seconds=299)
    assert not scheduler.tick(now[0])
    now[0] += timedelta(seconds=1)
    assert scheduler.tick(now[0])
    assert scheduler.read()["status"] == "succeeded"
    assert scheduler.read()["attempts"] == 2
    assert not scheduler.read()["needs_attention"]


def test_retry_limit_and_next_daily_cycle(tmp_path):
    now = [moment()]
    scheduler = Scheduler(
        tmp_path,
        Settings(),
        lambda _: Outcome("failed", True, "PipelineFailed"),
        lambda: now[0],
    )
    for _ in range(3):
        assert scheduler.tick(now[0])
        now[0] += timedelta(seconds=300)
    assert scheduler.read()["status"] == "failed"
    assert scheduler.read()["needs_attention"]
    assert not scheduler.tick(now[0])
    events = (tmp_path / "data/operations/events.jsonl").read_text(encoding="utf-8")
    assert len(events.splitlines()) == 6
    now[0] += timedelta(days=1)
    assert scheduler.tick(now[0])
    assert scheduler.read()["attempts"] == 1


def test_validation_failure_does_not_retry(tmp_path):
    scheduler = Scheduler(
        tmp_path,
        Settings(),
        lambda _: Outcome("failed", False, "PayloadValidationError"),
        moment,
    )
    assert scheduler.tick(moment())
    assert scheduler.read()["needs_attention"]
    assert not scheduler.tick(moment() + timedelta(hours=2))
    assert scheduler.read()["attempts"] == 1


def test_interrupted_attempt_is_recovered_with_limit(tmp_path):
    scheduler = Scheduler(tmp_path, Settings(), lambda _: Outcome("succeeded"), moment)
    slot = scheduler.settings.latest_slot(moment()).isoformat()
    scheduler.save({"scheduled_for": slot, "attempts": 1, "status": "running"})
    assert scheduler.tick(moment())
    assert scheduler.read()["status"] == "succeeded"
    assert scheduler.read()["attempts"] == 2
    scheduler.save({"scheduled_for": slot, "attempts": 3, "status": "running"})
    assert not scheduler.tick(moment())
    assert scheduler.read()["status"] == "failed"
    assert scheduler.read()["error_type"] == "InterruptedExecution"


def test_instance_lock_releases_after_exception(tmp_path):
    path = tmp_path / "scheduler.lock"
    with pytest.raises(RuntimeError, match="test"), instance_lock(path):
        with pytest.raises(AlreadyRunning), instance_lock(path):
            pass
        raise RuntimeError("test")
    with instance_lock(path):
        pass


def test_executor_correlates_report_and_preserves_retry_policy(tmp_path, monkeypatch):
    execution_id = "1234"
    scheduler = Scheduler(tmp_path, Settings())

    def fake_run(command, **kwargs):
        assert command[-2:] == ["--execution-id", execution_id]
        report = tmp_path / "data/runs" / execution_id / "report.json"
        report.parent.mkdir(parents=True)
        report.write_text(
            json.dumps(
                {
                    "status": "skipped",
                    "retryable": True,
                    "error_type": "PipelineBusyError",
                }
            ),
            encoding="utf-8",
        )
        return CompletedProcess(command, 2)

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    assert scheduler.run_pipeline(execution_id) == Outcome(
        "failed", True, "PipelineBusyError"
    )


def test_missing_report_is_operational_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(
        module.subprocess, "run", lambda *a, **k: CompletedProcess(a[0], 1)
    )
    scheduler = Scheduler(tmp_path, Settings())
    assert scheduler.run_pipeline("missing") == Outcome(
        "failed", True, "MissingExecutionReport"
    )


@pytest.mark.parametrize(
    "values",
    [
        {"hour": 24},
        {"minute": 60},
        {"max_attempts": 0},
        {"retry_seconds": 0},
    ],
)
def test_invalid_configuration(values):
    with pytest.raises(ValueError):
        Settings(**values)


def test_corrupt_state_is_not_silently_reset(tmp_path):
    scheduler = Scheduler(tmp_path, Settings())
    scheduler.path.write_text("broken", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        scheduler.tick(datetime.now(UTC))
