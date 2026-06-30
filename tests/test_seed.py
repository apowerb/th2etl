"""Tests for the default-pipelines seed (logic only, no real DB).

Uses a fake in-memory storage to verify what gets created, idempotence,
and that pipeline stages only reference seeded blocs.
"""
from __future__ import annotations

from th2etl.seeds.default_pipelines import (
    SEED_BLOCS,
    SEED_PIPELINES,
    seed_default_pipelines,
)


class FakeStorage:
    def __init__(self) -> None:
        self.blocs: dict[str, dict] = {}
        self.pipelines: dict[str, dict] = {}

    def get_bloc(self, name: str):
        return self.blocs.get(name)

    def create_bloc(self, name, bloc_type, config=None, description=None):
        if name in self.blocs:
            raise AssertionError(f"create_bloc called twice for {name}")
        self.blocs[name] = {"bloc_type": bloc_type, "config": config, "description": description}

    def get_pipeline(self, name: str):
        return self.pipelines.get(name)

    def create_pipeline(self, name, stages, description=None):
        if name in self.pipelines:
            raise AssertionError(f"create_pipeline called twice for {name}")
        # mimic the real storage (_ensure_blocs_exist raises ValueError):
        # every referenced bloc must already exist
        for stage in stages:
            for bloc_name in stage:
                if bloc_name not in self.blocs:
                    raise ValueError(f"bloc {bloc_name} must exist before pipeline {name}")
        self.pipelines[name] = {"stages": stages, "description": description}


def test_seed_creates_all_on_empty_storage():
    storage = FakeStorage()
    summary = seed_default_pipelines(storage)

    assert set(summary["blocs_created"]) == {"agents_runner", "pdf_extract", "pdf_agent"}
    assert set(summary["pipelines_created"]) == {"agents", "process_pdf"}
    assert summary["blocs_skipped"] == []
    assert summary["pipelines_skipped"] == []
    assert set(storage.pipelines) == {"agents", "process_pdf"}


def test_seed_is_idempotent():
    storage = FakeStorage()
    seed_default_pipelines(storage)
    summary = seed_default_pipelines(storage)  # second run

    assert summary["blocs_created"] == []
    assert summary["pipelines_created"] == []
    assert set(summary["blocs_skipped"]) == {"agents_runner", "pdf_extract", "pdf_agent"}
    assert set(summary["pipelines_skipped"]) == {"agents", "process_pdf"}


def test_pipeline_stages_only_reference_seeded_blocs():
    seeded_bloc_names = {b["name"] for b in SEED_BLOCS}
    for pipeline in SEED_PIPELINES:
        for stage in pipeline["stages"]:
            for bloc_name in stage:
                assert bloc_name in seeded_bloc_names, f"{bloc_name} not seeded"
