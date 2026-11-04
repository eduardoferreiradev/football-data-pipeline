"""Daily local orchestration with durable state and bounded retries."""

import argparse
import json
import os
import signal
import subprocess
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event
from uuid import uuid4
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


class AlreadyRunning(RuntimeError):
    pass


@contextmanager
def instance_lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        if path.stat().st_size == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise AlreadyRunning("Scheduler lock is held.") from exc
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@dataclass(frozen=True)
class Settings:
    timezone: str = "America/Sao_Paulo"
    hour: int = 6
    minute: int = 0
    max_attempts: int = 3
    retry_seconds: int = 300

    def __post_init__(self):
        ZoneInfo(self.timezone)
        if not (0 <= self.hour <= 23 and 0 <= self.minute <= 59):
            raise ValueError("Invalid daily time.")
        if not 1 <= self.max_attempts <= 10 or self.retry_seconds < 1:
            raise ValueError("Invalid retry settings.")

    @classmethod
    def from_env(cls):
        return cls(
            timezone=os.getenv("PIPELINE_TIMEZONE", "America/Sao_Paulo"),
            hour=int(os.getenv("PIPELINE_DAILY_HOUR", "6")),
            minute=int(os.getenv("PIPELINE_DAILY_MINUTE", "0")),
            max_attempts=int(os.getenv("PIPELINE_MAX_ATTEMPTS", "3")),
            retry_seconds=int(os.getenv("PIPELINE_RETRY_SECONDS", "300")),
        )

    def latest_slot(self, now):
        local = now.astimezone(ZoneInfo(self.timezone))
        slot = local.replace(
            hour=self.hour, minute=self.minute, second=0, microsecond=0
        )
        return slot if local >= slot else slot - timedelta(days=1)


@dataclass(frozen=True)
class Outcome:
    status: str
    retryable: bool = False
    error_type: str | None = None


class Scheduler:
    def __init__(self, root, settings, execute=None, clock=None):
        self.root = root
        self.clock = clock or (lambda: datetime.now(UTC))
        self.settings = settings
        self.operations = root / "data/operations"
        self.operations.mkdir(parents=True, exist_ok=True)
        self.path = self.operations / "status.json"
        self.execute = execute or self.run_pipeline

    def read(self):
        return (
            json.loads(self.path.read_text(encoding="utf-8"))
            if self.path.exists()
            else {}
        )

    def save(self, state):
        state["needs_attention"] = state["status"] == "failed"
        temporary = self.path.with_suffix("." + uuid4().hex + ".tmp")
        temporary.write_text(json.dumps(state, indent=2), encoding="utf-8")
        temporary.replace(self.path)
        with (self.operations / "events.jsonl").open("a", encoding="utf-8") as log:
            log.write(json.dumps(state) + "\n")
        print(json.dumps(state), flush=True)

    def run_pipeline(self, execution_id):
        log_path = self.operations / (execution_id + ".log")
        try:
            with log_path.open("w", encoding="utf-8") as log:
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "src.run_pipeline",
                        "--execution-id",
                        execution_id,
                    ],
                    cwd=self.root,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                )
            report_path = self.root / "data/runs" / execution_id / "report.json"
            if not report_path.exists():
                return Outcome("failed", True, "MissingExecutionReport")
            report = json.loads(report_path.read_text(encoding="utf-8"))
            if result.returncode == 0 and report["status"] == "succeeded":
                return Outcome("succeeded")
            return Outcome(
                "failed",
                report.get("retryable", False),
                report.get("error_type", "PipelineFailed"),
            )
        except (OSError, ValueError):
            return Outcome("failed", True, "ExecutionInfrastructureError")

    def tick(self, now):
        slot = self.settings.latest_slot(now)
        state = self.read()
        if (
            state.get("scheduled_for")
            and datetime.fromisoformat(state["scheduled_for"]) > slot
        ):
            return False
        if state.get("scheduled_for") != slot.isoformat():
            state = {
                "scheduled_for": slot.isoformat(),
                "attempts": 0,
                "status": "pending",
                "next_scheduled_for": (slot + timedelta(days=1)).isoformat(),
            }
        if state["status"] in ("succeeded", "failed"):
            return False
        # A process interrupted after claiming an attempt must not remain "running".
        if state["status"] == "running":
            state.update(
                status="retry_wait",
                error_type="InterruptedExecution",
                retry_at=now.isoformat(),
            )
        if state["attempts"] >= self.settings.max_attempts:
            state.update(status="failed", updated_at=now.isoformat())
            self.save(state)
            return False
        if state.get("retry_at") and now < datetime.fromisoformat(state["retry_at"]):
            return False
        execution_id = str(uuid4())
        state.update(
            status="running",
            attempts=state["attempts"] + 1,
            execution_id=execution_id,
            updated_at=now.isoformat(),
            report_path=f"data/runs/{execution_id}/report.json",
            log_path=f"data/operations/{execution_id}.log",
        )
        self.save(state)
        outcome = self.execute(execution_id)
        finished = self.clock()
        state.update(
            status=outcome.status,
            error_type=outcome.error_type,
            updated_at=finished.isoformat(),
        )
        state.pop("retry_at", None)
        if outcome.status != "succeeded":
            state["status"] = (
                "retry_wait"
                if outcome.retryable and state["attempts"] < self.settings.max_attempts
                else "failed"
            )
            if state["status"] == "retry_wait":
                state["retry_at"] = (
                    finished + timedelta(seconds=self.settings.retry_seconds)
                ).isoformat()
        self.save(state)
        return True


def main(argv=None):
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--once", action="store_true", help="Process the latest due slot."
    )
    parser.add_argument(
        "--status", action="store_true", help="Inspect durable local state."
    )
    args = parser.parse_args(argv)
    scheduler = Scheduler(ROOT, Settings.from_env())
    if args.status:
        print(json.dumps(scheduler.read(), indent=2))
        return 0
    stop = Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    try:
        with instance_lock(scheduler.operations / "scheduler.lock"):
            while not stop.is_set():
                scheduler.tick(datetime.now(UTC))
                if args.once:
                    return 1 if scheduler.read().get("needs_attention") else 0
                stop.wait(30)
    except AlreadyRunning:
        print(
            json.dumps({"status": "skipped", "error_type": "SchedulerAlreadyRunning"})
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
