"""Tests for execute_pipeline_run: the function that actually runs a pipeline
in the background and records its outcome (status transitions)."""
from __future__ import annotations

import pytest

import th2etl.pipelines.runner as runner_mod
from th2etl.pipelines.runner import execute_pipeline_run
from th2etl.storage.database import RunStatus


class RecordingStorage:
    def __init__(self) -> None:
        self.updates: list[dict] = []

    def update_pipeline_run(self, run_id: int, **fields):
        self.updates.append({"run_id": run_id, **fields})

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def close(self):
        pass


class _OkPipeline:
    def execute(self, run_context):
        return run_context


class _BoomPipeline:
    def execute(self, run_context):
        raise RuntimeError("bloc exploded")


@pytest.fixture
def storage(monkeypatch) -> RecordingStorage:
    s = RecordingStorage()
    monkeypatch.setattr(runner_mod.DatabaseStorage, "from_settings", staticmethod(lambda settings: s))
    return s


def _statuses(storage: RecordingStorage) -> list[str]:
    return [u["status"] for u in storage.updates if "status" in u]


def test_successful_run_transitions_running_then_success(storage, monkeypatch):
    monkeypatch.setattr(runner_mod, "build_pipeline_from_database", lambda st, name: _OkPipeline())
    execute_pipeline_run(run_id=1, pipeline_name="agents", variables={"x": 1})
    assert _statuses(storage) == [RunStatus.RUNNING.value, RunStatus.SUCCESS.value]


def test_failed_run_records_failure_and_error(storage, monkeypatch):
    monkeypatch.setattr(runner_mod, "build_pipeline_from_database", lambda st, name: _BoomPipeline())
    execute_pipeline_run(run_id=2, pipeline_name="agents", variables={})
    assert _statuses(storage) == [RunStatus.RUNNING.value, RunStatus.FAILED.value]
    last = storage.updates[-1]
    assert "bloc exploded" in (last.get("error") or "")


def test_run_marked_failed_when_pipeline_missing(storage, monkeypatch):
    """If the pipeline is deleted between trigger and execution, the run is
    marked failed (graceful) rather than left dangling."""
    def _raise(st, name):
        raise ValueError(f"Pipeline {name!r} does not exist")

    monkeypatch.setattr(runner_mod, "build_pipeline_from_database", _raise)
    execute_pipeline_run(run_id=9, pipeline_name="gone", variables={})
    assert _statuses(storage) == [RunStatus.RUNNING.value, RunStatus.FAILED.value]
    assert "does not exist" in (storage.updates[-1].get("error") or "")


def test_variables_are_passed_into_run_context(storage, monkeypatch):
    captured = {}

    class _CapturePipeline:
        def execute(self, run_context):
            captured["vars"] = dict(run_context.context_vars)
            return run_context

    monkeypatch.setattr(runner_mod, "build_pipeline_from_database", lambda st, name: _CapturePipeline())
    execute_pipeline_run(run_id=3, pipeline_name="agents", variables={"user_id": 42})
    assert captured["vars"]["user_id"] == 42
