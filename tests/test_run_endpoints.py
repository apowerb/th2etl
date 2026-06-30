"""Tests for the top-level run endpoints (GET /runs/{id}, POST /runs/{id}/cancel)
and GET /schedulers/{name}/runs."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from th2etl.main import app, get_db as main_get_db
from th2etl.routers.runs import get_db as runs_get_db
from th2etl.routers.schedulers import get_db as sched_get_db
from th2etl.storage.database import RunRecord, RunStatus, SchedulerRecord


def _run(run_id=5, status=RunStatus.PENDING.value, scheduler_name="agent42"):
    return RunRecord(
        id=run_id, pipeline_name="agents", status=status,
        variables={"jwt_token": "SECRET"}, result=None,
        error=None, scheduler_name=scheduler_name, created_at="", updated_at="",
        started_at=None, finished_at=None,
    )


class _FakeStorage:
    def __init__(self) -> None:
        self.cancelled: int | None = None

    def get_pipeline_run(self, run_id):
        return None if run_id == 404 else _run(run_id)

    def cancel_pipeline_run(self, run_id):
        if run_id == 404:
            return None
        self.cancelled = run_id
        return _run(run_id, status=RunStatus.CANCELLED.value)

    def get_scheduler(self, name):
        if name == "missing":
            return None
        return SchedulerRecord(
            id=1, name=name, pipeline_name="agents", trigger_name="t", description=None,
            variables={}, active=True, created_at="", updated_at="",
        )

    def list_scheduler_runs(self, scheduler_name, limit=50):
        return [_run(1, scheduler_name=scheduler_name), _run(2, scheduler_name=scheduler_name)]


@pytest.fixture
def client():
    fake = _FakeStorage()
    app.dependency_overrides[main_get_db] = lambda: fake
    app.dependency_overrides[runs_get_db] = lambda: fake
    app.dependency_overrides[sched_get_db] = lambda: fake
    c = TestClient(app)
    c.fake = fake  # type: ignore[attr-defined]
    yield c
    app.dependency_overrides.clear()


def test_get_run_by_id(client):
    resp = client.get("/runs/5")
    assert resp.status_code == 200
    assert resp.json()["id"] == 5
    assert "variables" not in resp.json()  # secrets never returned


def test_run_endpoints_never_leak_variables(client):
    assert "variables" not in client.post("/runs/5/cancel").json()
    assert all("variables" not in r for r in client.get("/schedulers/agent42/runs").json())


def test_get_run_404(client):
    assert client.get("/runs/404").status_code == 404


def test_cancel_run(client):
    resp = client.post("/runs/5/cancel")
    assert resp.status_code == 200
    assert resp.json()["status"] == RunStatus.CANCELLED.value
    assert client.fake.cancelled == 5


def test_cancel_run_404(client):
    assert client.post("/runs/404/cancel").status_code == 404


def test_list_scheduler_runs(client):
    resp = client.get("/schedulers/agent42/runs")
    assert resp.status_code == 200
    assert len(resp.json()) == 2
    assert all(r["scheduler_name"] == "agent42" for r in resp.json())


def test_list_scheduler_runs_unknown_404(client):
    assert client.get("/schedulers/missing/runs").status_code == 404
