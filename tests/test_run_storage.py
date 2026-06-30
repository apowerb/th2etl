"""Pins the dynamic SET-clause SQL built by update_pipeline_run, without a
real database (DatabaseStorage instantiated via __new__ + a fake connection
that captures the query and params)."""
from __future__ import annotations

from datetime import datetime

from th2etl.storage.database import DatabaseStorage


class _FakeCursor:
    def __init__(self, captured: dict, row: dict) -> None:
        self.captured = captured
        self.row = row
        self.description = True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, query, params=()):
        self.captured["query"] = query
        self.captured["params"] = params

    def fetchone(self):
        return self.row


class _FakeConn:
    def __init__(self, captured: dict, row: dict) -> None:
        self.captured = captured
        self.row = row

    def cursor(self):
        return _FakeCursor(self.captured, self.row)

    def commit(self):
        self.captured["committed"] = True


def _full_row() -> dict:
    now = datetime(2026, 6, 30, 12, 0, 0)
    return {
        "id": 5, "pipeline_name": "agents", "status": "success",
        "variables": {}, "result": None, "error": None,
        "created_at": now, "updated_at": now, "started_at": now, "finished_at": now,
    }


def _storage(captured: dict) -> DatabaseStorage:
    storage = DatabaseStorage.__new__(DatabaseStorage)  # bypass real connect()
    storage.schema = None
    storage.connection = _FakeConn(captured, _full_row())
    return storage


def test_update_pipeline_run_builds_set_clause_and_commits():
    captured: dict = {}
    rec = _storage(captured).update_pipeline_run(
        5, status="success", finished_at="2026-06-30T12:00:00"
    )
    q = captured["query"]
    assert "UPDATE etl_pipeline_runs SET" in q
    assert "updated_at = %s" in q  # always set
    assert "status = %s" in q
    assert "finished_at = %s" in q
    assert q.strip().endswith("WHERE id = %s RETURNING *")
    assert captured["params"][-1] == 5  # run_id is the last bound param
    assert captured["committed"] is True
    assert rec.id == 5 and rec.status == "success"


def test_update_pipeline_run_only_sets_provided_fields():
    captured: dict = {}
    _storage(captured).update_pipeline_run(5, status="running")
    q = captured["query"]
    assert "status = %s" in q
    # fields not passed must not appear in the SET clause
    assert "error = %s" not in q
    assert "result = %s" not in q
    assert "finished_at = %s" not in q
