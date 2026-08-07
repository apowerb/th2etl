"""A migration that cannot take its lock must give up, not queue.

`ALTER TABLE ... ADD COLUMN IF NOT EXISTS` still takes an ACCESS EXCLUSIVE lock
when the column is already present. Postgres grants locks in order, so a request
waiting for one blocks every reader that arrives after it. Seeding production on
2026-08-07 queued behind an idle-in-transaction session and froze
`etl_schedulers` for ten minutes -- a table nobody was writing to.

Every column these statements add is also declared in CREATE TABLE, so a fresh
database is already correct and giving up costs nothing. A legacy database
retries on the next boot.
"""

from __future__ import annotations

import psycopg
import pytest

from th2etl.storage.database import MIGRATION_LOCK_TIMEOUT, DatabaseStorage


class _Cursor:
    def __init__(self, recorder: list[str], raise_on_alter: bool = False):
        self._recorder = recorder
        self._raise = raise_on_alter

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, statement, *args, **kwargs):
        self._recorder.append(statement)
        if self._raise and statement.lstrip().upper().startswith("ALTER TABLE"):
            raise psycopg.errors.LockNotAvailable("lock timeout")


class _Connection:
    def __init__(self, raise_on_alter: bool = False):
        self.statements: list[str] = []
        self.commits = 0
        self.rollbacks = 0
        self._raise = raise_on_alter

    def cursor(self):
        return _Cursor(self.statements, self._raise)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def _storage(conn) -> DatabaseStorage:
    storage = DatabaseStorage.__new__(DatabaseStorage)
    storage.connection = conn
    storage.schema = None
    return storage


@pytest.fixture(autouse=True)
def _fresh_process_flag():
    DatabaseStorage._migrated = False
    yield
    DatabaseStorage._migrated = False


def test_the_lock_wait_is_bounded_before_any_alter_runs():
    """Without this, the ALTER inherits the session default: wait forever."""
    conn = _Connection()
    _storage(conn)._apply_migrations("etl_schedulers")

    assert conn.statements, "aucune instruction emise"
    first = conn.statements[0]
    assert "lock_timeout" in first, f"la premiere instruction devrait borner le verrou : {first}"
    assert MIGRATION_LOCK_TIMEOUT in first
    assert first.index("lock_timeout") >= 0
    for statement in conn.statements[1:]:
        assert statement.lstrip().upper().startswith("ALTER TABLE")


def test_a_successful_run_commits_and_never_repeats():
    conn = _Connection()
    storage = _storage(conn)

    storage._apply_migrations("etl_schedulers")
    assert conn.commits == 1
    assert DatabaseStorage._migrated is True

    before = len(conn.statements)
    storage._apply_migrations("etl_schedulers")
    assert len(conn.statements) == before, "les migrations ont rejoue"


def test_giving_up_rolls_back_and_leaves_the_retry_open():
    """The next boot must try again -- and nothing may stay half-applied."""
    conn = _Connection(raise_on_alter=True)

    _storage(conn)._apply_migrations("etl_schedulers")

    assert conn.rollbacks == 1, "la transaction doit etre annulee"
    assert conn.commits == 0
    assert DatabaseStorage._migrated is False, "un abandon ne doit pas passer pour un succes"


def test_giving_up_is_not_silent(caplog):
    """A skipped migration that logs nothing is indistinguishable from a done one."""
    import logging

    conn = _Connection(raise_on_alter=True)
    with caplog.at_level(logging.WARNING, logger="th2etl.storage.database"):
        _storage(conn)._apply_migrations("etl_schedulers")

    assert "migrations skipped" in caplog.text
    assert MIGRATION_LOCK_TIMEOUT in caplog.text
