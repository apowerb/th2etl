"""Persisting structured run events to a queryable store: the RunLogHandler
(record -> row), the list_run_logs SQL, and the GET /runs/{id}/logs +
GET /schedulers/{name}/runs/{id}/logs endpoints. No real database — the DB write
is an injected callable and the SQL is captured via a fake connection."""
from __future__ import annotations

import datetime as dt
import logging
import threading

import pytest
from fastapi.testclient import TestClient

from conftest import AUTH_HEADER

from th2etl.configs.run_logging import RunLogHandler
from th2etl.storage.run_log_writer import RunLogWriter
from th2etl.main import app, get_db as main_get_db
from th2etl.routers.runs import get_db as runs_get_db
from th2etl.routers.schedulers import get_db as sched_get_db
from th2etl.storage.database import (
    DatabaseStorage,
    RunLogRecord,
    RunRecord,
    RunStatus,
    SchedulerRecord,
)


def _record(event="run.worker_started", **extra) -> logging.LogRecord:
    rec = logging.makeLogRecord(
        {"name": "th2etl.pipelines", "levelname": "INFO", "levelno": logging.INFO, "msg": event}
    )
    rec.event = event
    for k, v in extra.items():
        setattr(rec, k, v)
    return rec


# --- RunLogHandler ---------------------------------------------------------

def test_handler_persists_event_with_run_id_and_promotes_fields():
    rows: list = []
    RunLogHandler(rows.append).emit(
        _record("bloc.end", run_id=7, bloc="run_agent", step=2, duration_ms=12)
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["run_id"] == 7
    assert row["event"] == "bloc.end"
    assert row["level"] == "INFO"
    assert row["message"] == "bloc.end"
    # ambient/extra fields land in the JSONB `fields`, not as reserved noise
    assert row["fields"] == {"bloc": "run_agent", "step": 2, "duration_ms": 12}
    assert "run_id" not in row["fields"] and "event" not in row["fields"]
    assert row["ts"].tzinfo is not None  # tz-aware UTC timestamp


def test_handler_skips_record_without_run_id():
    rows: list = []
    RunLogHandler(rows.append).emit(_record("run.created"))  # no run_id
    assert rows == []


def test_handler_skips_non_event_record():
    rows: list = []
    rec = logging.makeLogRecord(
        {"name": "uvicorn", "levelname": "INFO", "levelno": logging.INFO, "msg": "plain line"}
    )
    rec.run_id = 9  # has run_id but no `event` -> not a structured event
    RunLogHandler(rows.append).emit(rec)
    assert rows == []


def test_handler_is_fault_tolerant_when_write_fails():
    """A failing store must never crash the run: emit routes the error through
    handleError and does not propagate."""
    def boom(_row):
        raise RuntimeError("db down")

    handler = RunLogHandler(boom)
    seen: list = []
    handler.handleError = lambda record: seen.append(record)  # type: ignore[assignment]
    handler.emit(_record("run.worker_failed", run_id=1))  # must not raise
    assert len(seen) == 1


# --- RunLogWriter (no real DB) ---------------------------------------------

class _WCursor:
    def __init__(self, captured, fail):
        self.captured, self.fail = captured, fail

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, query, params=()):
        self.captured.setdefault("executes", []).append((query, params))
        if self.fail:
            raise RuntimeError("server-side error mid-statement")


class _WConn:
    def __init__(self, captured, fail):
        self.captured, self.fail = captured, fail

    def cursor(self):
        return _WCursor(self.captured, self.fail)

    def rollback(self):
        self.captured["rolled_back"] = True


def _writer(captured, fail=False) -> RunLogWriter:
    w = RunLogWriter.__new__(RunLogWriter)  # bypass real psycopg.connect
    w._table = "etl_pipeline_run_logs"
    w._index = "etl_pipeline_run_logs"
    w._lock = threading.Lock()
    w._conn = _WConn(captured, fail)
    return w


def _row(**over):
    base = {"run_id": 7, "ts": dt.datetime(2026, 7, 2, tzinfo=dt.timezone.utc),
            "level": "INFO", "event": "run.created", "message": "m", "fields": {"source": "api"}}
    base.update(over)
    return base


def test_writer_inserts_event_and_does_not_rollback_on_success():
    captured: dict = {}
    _writer(captured).write(_row())
    q, params = captured["executes"][0]
    assert "INSERT INTO etl_pipeline_run_logs" in q
    assert params[0] == 7 and params[3] == "run.created"
    assert "rolled_back" not in captured  # healthy write leaves no rollback


def test_writer_rolls_back_and_reraises_on_failure():
    """The finding: without a rollback, a single server-side error poisons the
    long-lived connection for the rest of the process. The writer must roll back
    (leaving the connection usable) AND re-raise so the handler logs it."""
    captured: dict = {}
    with pytest.raises(RuntimeError):
        _writer(captured, fail=True).write(_row())
    assert captured["rolled_back"] is True


# --- list_run_logs SQL (no real DB) ----------------------------------------

class _FakeCursor:
    def __init__(self, captured, rows):
        self.captured, self.rows, self.description = captured, rows, True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, query, params=()):
        self.captured["query"], self.captured["params"] = query, params

    def fetchall(self):
        return self.rows


class _FakeConn:
    def __init__(self, captured, rows):
        self.captured, self.rows = captured, rows

    def cursor(self):
        return _FakeCursor(self.captured, self.rows)


def test_list_run_logs_queries_by_run_id_in_order():
    captured: dict = {}
    ts = dt.datetime(2026, 7, 2, 10, 0, 0, tzinfo=dt.timezone.utc)
    row = {"id": 1, "run_id": 7, "ts": ts, "level": "INFO", "event": "run.created",
           "message": "run.created", "fields": {"source": "api"}}
    storage = DatabaseStorage.__new__(DatabaseStorage)
    storage.schema = None
    storage.connection = _FakeConn(captured, [row])

    logs = storage.list_run_logs(7, limit=100)
    q = captured["query"]
    assert "FROM etl_pipeline_run_logs" in q
    assert "WHERE run_id = %s" in q
    assert "ORDER BY id ASC" in q
    assert captured["params"] == (7, 100)
    assert logs == [RunLogRecord(id=1, run_id=7, ts=ts.isoformat(), level="INFO",
                                 event="run.created", message="run.created",
                                 fields={"source": "api"})]


# --- endpoints -------------------------------------------------------------

def _run(run_id=5, scheduler_name="agent42"):
    return RunRecord(
        id=run_id, pipeline_name="agents", status=RunStatus.SUCCESS.value,
        variables={"jwt_token": "SECRET"}, result=None, error=None,
        scheduler_name=scheduler_name, created_at="", updated_at="",
        started_at=None, finished_at=None,
    )


class _FakeStorage:
    def get_pipeline_run(self, run_id):
        return None if run_id == 404 else _run(run_id)

    def get_scheduler(self, name):
        if name == "missing":
            return None
        return SchedulerRecord(id=1, name=name, pipeline_name="agents", trigger_name="t",
                               description=None, variables={}, active=True,
                               created_at="", updated_at="")

    def list_run_logs(self, run_id, limit=500):
        return [
            RunLogRecord(id=1, run_id=run_id, ts="2026-07-02T10:00:00+00:00", level="INFO",
                         event="run.created", message="run.created", fields={"source": "api"}),
            RunLogRecord(id=2, run_id=run_id, ts="2026-07-02T10:00:01+00:00", level="INFO",
                         event="bloc.end", message="bloc.end", fields={"bloc": "run_agent"}),
        ]


@pytest.fixture
def client():
    fake = _FakeStorage()
    app.dependency_overrides[main_get_db] = lambda: fake
    app.dependency_overrides[runs_get_db] = lambda: fake
    app.dependency_overrides[sched_get_db] = lambda: fake
    c = TestClient(app, headers=AUTH_HEADER)
    yield c
    app.dependency_overrides.clear()


def test_get_run_logs_returns_ordered_events(client):
    resp = client.get("/runs/5/logs")
    assert resp.status_code == 200
    body = resp.json()
    assert [e["event"] for e in body] == ["run.created", "bloc.end"]
    assert body[1]["fields"]["bloc"] == "run_agent"


def test_get_run_logs_404_when_run_missing(client):
    assert client.get("/runs/404/logs").status_code == 404


def test_scheduler_run_logs_ok(client):
    resp = client.get("/schedulers/agent42/runs/5/logs")
    assert resp.status_code == 200
    assert [e["event"] for e in resp.json()] == ["run.created", "bloc.end"]


def test_scheduler_run_logs_404_unknown_scheduler(client):
    assert client.get("/schedulers/missing/runs/5/logs").status_code == 404


def test_scheduler_run_logs_404_run_of_other_scheduler(client):
    # run 5 belongs to scheduler 'agent42'; asking under 'other' must 404
    assert client.get("/schedulers/other/runs/5/logs").status_code == 404
