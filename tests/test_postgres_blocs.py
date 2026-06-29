"""Tests for the PostgreSQL loader/exporter blocs.

These pin the bug fixes:
- the blocs must be constructible via the factory (config dict), like every
  other bloc, instead of crashing on a positional-arg signature;
- execute() must use RunContext.context_vars (not the removed get/set_data
  + get_database_settings API);
- postgres_exporter must be registered as a factory.

A fake SQLAlchemy engine + monkeypatched pandas avoid any real DB.
"""
from __future__ import annotations

import pandas as pd
import pytest

import th2etl.blocs.postgresql as pg
from th2etl.blocs.postgresql import PostgresExporterBloc, PostgresLoaderBloc
from th2etl.pipelines.context import RunContext
from th2etl.pipelines.pipeline import build_bloc_from_record


class _FakeConn:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def fake_engine(monkeypatch):
    monkeypatch.setattr(pg, "create_engine", lambda dsn: type("E", (), {"connect": lambda self: _FakeConn()})())


def test_postgres_loader_built_from_factory():
    bloc = build_bloc_from_record("pg", "postgres_loader", {"query": "SELECT 1"})
    assert isinstance(bloc, PostgresLoaderBloc)


def test_postgres_exporter_registered_and_built_from_factory():
    bloc = build_bloc_from_record("exp", "postgres_exporter", {"table_name": "t", "source_bloc": "src"})
    assert isinstance(bloc, PostgresExporterBloc)


def test_loader_execute_puts_rows_in_context(monkeypatch, fake_engine):
    monkeypatch.setattr(pg.pd, "read_sql", lambda query, conn: pd.DataFrame([{"id": 1, "value": 2}]))
    bloc = PostgresLoaderBloc("pg", {"query": "SELECT * FROM t"})
    ctx = RunContext()
    bloc.execute(ctx)
    assert ctx.context_vars["pg_data"] == [{"id": 1, "value": 2}]


def test_exporter_writes_source_bloc_data(monkeypatch, fake_engine):
    captured = {}
    monkeypatch.setattr(
        pd.DataFrame, "to_sql",
        lambda self, table, conn, **kw: captured.update(table=table, rows=len(self), if_exists=kw.get("if_exists")),
    )
    ctx = RunContext()
    ctx.context_vars["src_data"] = [{"id": 1}, {"id": 2}]
    bloc = PostgresExporterBloc("exp", {"table_name": "dest", "source_bloc": "src"})
    bloc.execute(ctx)
    assert captured == {"table": "dest", "rows": 2, "if_exists": "replace"}


def test_exporter_missing_source_raises(fake_engine):
    bloc = PostgresExporterBloc("exp", {"table_name": "dest", "source_bloc": "absent"})
    with pytest.raises(ValueError):
        bloc.execute(RunContext())


def test_type_hint_names_imported_in_scheduler_helpers():
    """Settings and SchedulerRecord are referenced in type hints; they must be
    importable from the module (not undefined names)."""
    import th2etl.scheduler.helpers as helpers

    assert hasattr(helpers, "Settings")
    assert hasattr(helpers, "SchedulerRecord")
