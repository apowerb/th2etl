"""Per-scheduler runtime variables + active flag: variables are injected into
the run context when the cron fires, inactive schedulers don't run, and the
ad-hoc run-now endpoint merges stored variables with request overrides."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from th2etl.main import app, get_db as main_get_db
from th2etl.routers.schedulers import get_db as sched_get_db
import th2etl.routers.schedulers as sched_router
from th2etl.scheduler.helpers import CronScheduler, CronTrigger, SchedulerManager
from th2etl.storage.database import RunRecord, RunStatus, SchedulerRecord


class _FakePipeline:
    def __init__(self) -> None:
        self.seen: dict | None = None

    def execute(self, run_context):
        self.seen = dict(run_context.context_vars)
        return run_context


def _sched(pipeline, *, name="s", variables=None, active=True) -> CronScheduler:
    return CronScheduler(
        pipeline=pipeline,
        trigger=CronTrigger("* * * * *"),
        name=name,
        variables=variables,
        active=active,
    )


def test_variables_injected_into_run_context_on_fire():
    pipe = _FakePipeline()
    _sched(pipe, variables={"agent_id": "7", "jwt_token": "abc"}).run_once()
    assert pipe.seen == {"agent_id": "7", "jwt_token": "abc"}


def test_inactive_scheduler_does_not_run():
    pipe = _FakePipeline()
    sched = _sched(pipe, active=False)
    assert sched.run_pending() is False
    assert pipe.seen is None


def test_manager_skips_inactive_schedulers():
    active_pipe, inactive_pipe = _FakePipeline(), _FakePipeline()
    active = _sched(active_pipe, name="a", active=True)
    inactive = _sched(inactive_pipe, name="i", active=False)
    manager = SchedulerManager(schedulers=[active, inactive])
    try:
        futures = manager.run_pending()  # both are due ("* * * * *")
        for f in futures:
            f.result()
        assert len(futures) == 1  # only the active one dispatched
        assert active_pipe.seen is not None
        assert inactive_pipe.seen is None
    finally:
        manager.executor.shutdown(wait=True)


# --- router: ad-hoc run-now merges stored + request variables ---

class _FakeStorage:
    def __init__(self) -> None:
        self.created_run_vars: dict | None = None

    def get_scheduler(self, name: str):
        if name == "missing":
            return None
        return SchedulerRecord(
            id=1, name=name, pipeline_name="agents", trigger_name="t", description=None,
            variables={"agent_id": "stored", "jwt_token": "old"}, active=True,
            created_at="", updated_at="",
        )

    def create_pipeline_run(self, pipeline_name, variables=None):
        self.created_run_vars = variables
        return RunRecord(
            id=99, pipeline_name=pipeline_name, status=RunStatus.PENDING.value,
            variables=variables or {}, result=None, error=None,
            created_at="", updated_at="", started_at=None, finished_at=None,
        )


@pytest.fixture
def client(monkeypatch):
    fake = _FakeStorage()
    scheduled = []
    monkeypatch.setattr(
        sched_router, "execute_pipeline_run",
        lambda run_id, pipeline_name, variables: scheduled.append((run_id, pipeline_name, variables)),
    )
    app.dependency_overrides[main_get_db] = lambda: fake
    app.dependency_overrides[sched_get_db] = lambda: fake
    c = TestClient(app)
    c.fake = fake  # type: ignore[attr-defined]
    c.scheduled = scheduled  # type: ignore[attr-defined]
    yield c
    app.dependency_overrides.clear()


def test_run_now_merges_stored_and_request_variables(client):
    resp = client.post("/schedulers/s1/run", json={"variables": {"jwt_token": "new", "extra": "x"}})
    assert resp.status_code == 202
    expected = {"agent_id": "stored", "jwt_token": "new", "extra": "x"}  # request overrides stored
    assert client.fake.created_run_vars == expected
    assert client.scheduled[0] == (99, "agents", expected)


def test_run_now_unknown_scheduler_404(client):
    assert client.post("/schedulers/missing/run", json={}).status_code == 404
