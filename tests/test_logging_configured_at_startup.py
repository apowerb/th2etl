"""Logging must be configured whatever the entrypoint, not just the CLI runner.

The deployed API is started as ``uvicorn th2etl.main:app``, which never goes
through ``runner.main()`` -- the only caller of ``setup_logging()`` until
2026-08-07. So on the servers nothing configured the run logging: no
JsonFormatter, no RunContextFilter, no RunLogHandler. Release v0.0.10 shipped
the queryable run log and the dev VM still recorded nothing -- run 426
succeeded and left zero rows in etl_pipeline_run_logs.
"""
from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from importlib import import_module

from th2etl.configs import logger as logger_module

# import th2etl.main as main would bind the runner's main function:
# th2etl/__init__.py re-exports it, shadowing the submodule of the same name.
main = import_module("th2etl.main")


class _FakeManager:
    """A scheduler manager that starts and stops without touching anything."""

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass


class _FakeStorage:
    def close(self) -> None:
        pass


@pytest.fixture
def api(monkeypatch):
    """The app with its database and scheduler replaced, so startup is cheap."""
    monkeypatch.setattr(
        main.DatabaseStorage, "from_settings", classmethod(lambda cls, settings: _FakeStorage())
    )
    monkeypatch.setattr(main, "load_scheduler_manager", lambda storage, settings=None: _FakeManager())
    return main.app


def test_starting_the_api_configures_logging(monkeypatch, api):
    """The regression this file exists for: uvicorn starting without any setup."""
    calls = []
    monkeypatch.setattr(main, "setup_logging", lambda: calls.append(True))

    with TestClient(api):
        pass

    assert calls, "the API started without configuring logging"


def test_configuring_twice_keeps_the_first_handlers(monkeypatch):
    """The runner and the API both call it; the second must not tear down the first.

    Rebuilding would drop the RunLogHandler built by the first call and leak the
    database connection its writer holds.
    """
    logger_module.setup_logging(force=True)
    handlers = list(logging.getLogger().handlers)

    logger_module.setup_logging()

    assert logging.getLogger().handlers == handlers


def test_force_rebuilds_deliberately():
    logger_module.setup_logging(force=True)
    before = list(logging.getLogger().handlers)

    logger_module.setup_logging(force=True)

    assert logging.getLogger().handlers != before
