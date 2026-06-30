"""Tests for the ad-hoc pipeline run endpoint (POST /pipelines/{name}/run) and run tracking.

These tests use an in-memory fake storage injected via FastAPI dependency overrides,
so no real PostgreSQL connection is required.
"""
from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from th2etl.main import app, get_db as main_get_db
from th2etl.routers.pipelines import get_db as router_get_db
from th2etl.storage.database import PipelineRecord, RunRecord, RunStatus
import th2etl.routers.pipelines as pipelines_router


class FakeStorage:
    """Minimal in-memory storage implementing only what the run endpoint needs."""

    def __init__(self) -> None:
        self.pipelines: dict[str, PipelineRecord] = {}
        self.runs: dict[int, RunRecord] = {}
        self._run_seq = 0

    # --- pipelines ---
    def add_pipeline(self, name: str) -> None:
        now = datetime.utcnow().isoformat()
        self.pipelines[name] = PipelineRecord(
            id=len(self.pipelines) + 1, name=name, stages=[["b"]],
            description=None, created_at=now, updated_at=now,
        )

    def get_pipeline(self, name: str) -> PipelineRecord | None:
        return self.pipelines.get(name)

    # --- runs ---
    def create_pipeline_run(self, pipeline_name: str, variables: dict | None = None, scheduler_name=None) -> RunRecord:
        self._run_seq += 1
        now = datetime.utcnow().isoformat()
        run = RunRecord(
            id=self._run_seq, pipeline_name=pipeline_name, status=RunStatus.PENDING.value,
            variables=variables or {}, result=None, error=None, scheduler_name=scheduler_name,
            created_at=now, updated_at=now, started_at=None, finished_at=None,
        )
        self.runs[run.id] = run
        return run

    def get_pipeline_run(self, run_id: int) -> RunRecord | None:
        return self.runs.get(run_id)

    def list_pipeline_runs(self, pipeline_name: str, limit: int = 50) -> list[RunRecord]:
        self.last_limit = limit
        return [r for r in self.runs.values() if r.pipeline_name == pipeline_name]

    def update_pipeline_run(self, run_id: int, **fields) -> RunRecord:
        run = self.runs[run_id]
        for k, v in fields.items():
            setattr(run, k, v)
        return run


@pytest.fixture
def fake() -> FakeStorage:
    return FakeStorage()


@pytest.fixture
def client(fake: FakeStorage, monkeypatch):
    # Never actually execute a pipeline in the API tests: stub the background runner.
    calls = []
    monkeypatch.setattr(
        pipelines_router, "execute_pipeline_run",
        lambda run_id, pipeline_name, variables: calls.append((run_id, pipeline_name, variables)),
    )
    app.dependency_overrides[main_get_db] = lambda: fake
    app.dependency_overrides[router_get_db] = lambda: fake
    c = TestClient(app)
    c.scheduled_calls = calls  # type: ignore[attr-defined]
    yield c
    app.dependency_overrides.clear()


def test_run_pipeline_creates_run_and_returns_202(client, fake):
    fake.add_pipeline("agents")
    resp = client.post("/pipelines/agents/run", json={"variables": {"user_id": 7}})
    assert resp.status_code == 202
    body = resp.json()
    assert "run_id" in body
    assert body["status"] == RunStatus.PENDING.value
    assert body["pipeline_name"] == "agents"
    # the background execution was scheduled with the run id + variables
    assert client.scheduled_calls == [(body["run_id"], "agents", {"user_id": 7})]


def test_run_pipeline_without_variables_defaults_to_empty(client, fake):
    fake.add_pipeline("process_pdf")
    resp = client.post("/pipelines/process_pdf/run", json={})
    assert resp.status_code == 202
    assert client.scheduled_calls[0][2] == {}


def test_run_unknown_pipeline_returns_404(client):
    resp = client.post("/pipelines/nope/run", json={"variables": {}})
    assert resp.status_code == 404
    assert client.scheduled_calls == []


def test_get_run_status(client, fake):
    fake.add_pipeline("agents")
    run_id = client.post("/pipelines/agents/run", json={}).json()["run_id"]
    resp = client.get(f"/pipelines/agents/runs/{run_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == run_id
    assert resp.json()["status"] == RunStatus.PENDING.value


def test_get_unknown_run_returns_404(client, fake):
    fake.add_pipeline("agents")
    resp = client.get("/pipelines/agents/runs/9999")
    assert resp.status_code == 404


def test_list_runs(client, fake):
    fake.add_pipeline("agents")
    client.post("/pipelines/agents/run", json={})
    client.post("/pipelines/agents/run", json={})
    resp = client.get("/pipelines/agents/runs")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_list_runs_forwards_limit(client, fake):
    fake.add_pipeline("agents")
    resp = client.get("/pipelines/agents/runs?limit=5")
    assert resp.status_code == 200
    assert fake.last_limit == 5
