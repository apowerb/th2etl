"""Dedicated sink that persists structured run events to a queryable table so a
run's execution flow can be fetched per-run (``GET /runs/{id}/logs``).

It deliberately owns its OWN psycopg connection, separate from the request-scoped
``DatabaseStorage``:

* a logging handler emits from whatever thread produced the record (including the
  pipeline worker threads), and a psycopg connection is not safe to share across
  threads — so writes are serialised behind a lock on this single connection;
* it issues a bare ``INSERT`` and never calls :func:`log_event`, so persisting a
  log can never recurse back into the logging pipeline that produced it.

The connection runs in **autocommit** mode: each event is an independent insert,
so a single failed statement (a lock timeout, a network hiccup mid-statement)
cannot leave the long-lived connection in psycopg's aborted-transaction state and
silently kill every subsequent write — the exact failure a diagnostics feature
must not have. A defensive ``rollback()`` on error is belt-and-suspenders.

Construction opens the connection eagerly and ensures the table exists (idempotent
``CREATE TABLE IF NOT EXISTS``), mirroring how ``DatabaseStorage`` bootstraps.
"""
from __future__ import annotations

import json
import threading
from typing import Any

import psycopg

from th2etl.storage.database import qualified_table_name


class RunLogWriter:
    """Serialised writer for the ``etl_pipeline_run_logs`` table."""

    def __init__(self, dsn: str, schema: str | None = None) -> None:
        self._table = qualified_table_name("pipeline_run_logs", schema)
        self._index = self._table.replace(".", "_")
        self._lock = threading.Lock()
        # autocommit: a failed insert can't poison the next one (see module docs).
        self._conn = psycopg.connect(dsn, autocommit=True)
        self._ensure_table()

    def _ensure_table(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self._table} (
                    id SERIAL PRIMARY KEY,
                    run_id INTEGER NOT NULL,
                    ts TIMESTAMPTZ NOT NULL,
                    level TEXT NOT NULL,
                    event TEXT NOT NULL,
                    message TEXT,
                    fields JSONB NOT NULL DEFAULT '{{}}'
                );
                CREATE INDEX IF NOT EXISTS ix_{self._index}_run_id
                    ON {self._table}(run_id);
                """
            )

    def write(self, row: dict[str, Any]) -> None:
        """Insert one structured event. Called from the logging handler; a lock
        serialises concurrent emits from worker threads onto the single
        connection. On any failure the connection is rolled back (so it can never
        get stuck in an aborted-transaction state) and the error is re-raised for
        the handler to route through ``handleError``."""
        with self._lock:
            try:
                with self._conn.cursor() as cur:
                    cur.execute(
                        f"INSERT INTO {self._table} (run_id, ts, level, event, message, fields) "
                        f"VALUES (%s, %s, %s, %s, %s, %s)",
                        (
                            row["run_id"],
                            row["ts"],
                            row["level"],
                            row["event"],
                            row.get("message"),
                            json.dumps(row.get("fields") or {}, default=str),
                        ),
                    )
            except Exception:
                try:
                    self._conn.rollback()
                except Exception:
                    pass
                raise

    def close(self) -> None:
        with self._lock:
            self._conn.close()
