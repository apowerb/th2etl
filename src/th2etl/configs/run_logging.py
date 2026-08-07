"""Structured, correlatable run logging for th2etl.

A pipeline run flows through several layers (API/scheduler -> background worker
-> pipeline -> stages -> blocs -> outbound HTTP), and several of those layers
run in worker threads. Plain string logs there carry no ``run_id``, so a run
that gets stuck (e.g. left ``pending`` because the background task never
started, or ``running`` forever because an outbound call has no timeout) is
invisible.

This module provides three pieces to make every log line correlatable:

* an ambient run context stored in a :class:`contextvars.ContextVar`, bound with
  :func:`bind_run_context` and readable everywhere in the same context — and,
  crucially, in child threads that were submitted via
  ``contextvars.copy_context()`` (see ``Pipeline.execute``);
* :class:`RunContextFilter`, which injects those context fields onto every
  :class:`logging.LogRecord`;
* :class:`JsonFormatter`, which serialises each record as one JSON object per
  line, surfacing the context fields and any ``extra=`` fields as columns.

Use :func:`log_event` to emit a machine-readable lifecycle event
(``run.created``, ``run.worker_started``, ``bloc.http_call`` ...).
"""
from __future__ import annotations

import contextvars
import json
import logging
from datetime import datetime, timezone
from typing import Any

# Structured columns we promote from the ambient context onto each record.
# (Adding a new field to a log call via ``extra=`` also works without listing
# it here — JsonFormatter emits any non-reserved record attribute.)
CONTEXT_FIELDS: tuple[str, ...] = (
    "run_id",
    "pipeline",
    "scheduler_name",
    "agent_id",
    "step",
    "bloc",
    "bloc_type",
    "source",
)

# Attribute names already owned by LogRecord — passing any of these via
# ``extra=`` makes the logging module raise KeyError. log_event() renames
# colliding field names (``module`` -> ``ctx_module``) instead of crashing.
_RESERVED_RECORD_KEYS: frozenset[str] = frozenset(logging.makeLogRecord({}).__dict__) | {"event"}

# The ambient run context. Propagated to child threads via
# ``contextvars.copy_context()`` at submission time, NOT by plain thread start.
_run_context: contextvars.ContextVar[dict[str, Any]] = contextvars.ContextVar(
    "th2etl_run_context", default={}
)


def bind_run_context(**fields: Any) -> contextvars.Token:
    """Merge ``fields`` (skipping ``None`` values) into the ambient run context.

    Returns a token to restore the previous context via :func:`reset_run_context`.
    Never mutates the stored dict in place, so the shared default stays empty.
    """
    current = dict(_run_context.get())
    current.update({k: v for k, v in fields.items() if v is not None})
    return _run_context.set(current)


def reset_run_context(token: contextvars.Token) -> None:
    """Restore the context captured before the matching :func:`bind_run_context`."""
    _run_context.reset(token)


def get_run_context() -> dict[str, Any]:
    """Return a copy of the current ambient run context."""
    return dict(_run_context.get())


class RunContextFilter(logging.Filter):
    """Inject the ambient run-context fields onto every record.

    Applied to each handler so both the JSON and text formatters can surface
    ``run_id``/``pipeline``/... — including from worker threads that inherited
    the context through ``copy_context()``. An explicit ``extra=`` on the log
    call wins over the ambient value (``hasattr`` guard).
    """

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003 - logging API
        ctx = _run_context.get()
        for key, value in ctx.items():
            if not hasattr(record, key):
                setattr(record, key, value)
        return True


class JsonFormatter(logging.Formatter):
    """Serialise a record as one JSON object per line.

    Base envelope (``ts``/``level``/``logger``/``message``) plus every
    non-reserved record attribute (context fields from the filter and any
    ``extra=`` fields), so a new structured field needs no formatter change.
    """

    _RESERVED: frozenset[str] = frozenset(
        logging.makeLogRecord({}).__dict__
    ) | frozenset({"message", "asctime"})

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key in self._RESERVED or key.startswith("_"):
                continue
            payload.setdefault(key, value)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


class EventOnlyFilter(logging.Filter):
    """Pass only records emitted through :func:`log_event` (i.e. carrying an
    ``event`` attribute). Attached to the JSON run-log handler so it stays a
    clean structured-event stream and never captures third-party logs
    (uvicorn/psycopg) or free-text lines that may embed response bodies/tokens.
    """

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003 - logging API
        return hasattr(record, "event")


# Record attributes that are NOT structured run fields: the LogRecord machinery
# plus the columns the handler promotes to their own DB columns. Everything else
# on the record (stage/bloc/agent_id/duration_ms/http_status/...) lands in the
# ``fields`` JSONB so a new event field needs no schema change.
_HANDLER_RESERVED: frozenset[str] = (
    frozenset(logging.makeLogRecord({}).__dict__)
    | frozenset({"message", "asctime", "event", "run_id"})
)


class RunLogHandler(logging.Handler):
    """Persist structured run events to a queryable store, one row per event.

    Only records that carry BOTH an ``event`` (emitted via :func:`log_event`)
    and a ``run_id`` (bound in the ambient context and injected by
    :class:`RunContextFilter`) are persisted — a log with no ``run_id`` cannot be
    correlated to a run. The actual write is an injected callable, so the handler
    is unit-testable without a database. It is fault-tolerant: a write failure is
    routed through :meth:`handleError` and never propagates, so a saturated or
    unreachable log store can never break a running pipeline.
    """

    def __init__(self, write: Any, level: int = logging.NOTSET) -> None:
        super().__init__(level)
        self._write = write  # callable(row: dict) -> None

    def emit(self, record: logging.LogRecord) -> None:
        run_id = getattr(record, "run_id", None)
        if run_id is None or not getattr(record, "event", None):
            return
        try:
            self._write(self._row(record, run_id))
        except Exception:  # noqa: BLE001 - logging must never crash the caller
            self.handleError(record)

    @staticmethod
    def _row(record: logging.LogRecord, run_id: Any) -> dict[str, Any]:
        fields = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _HANDLER_RESERVED and not key.startswith("_")
        }
        return {
            "run_id": run_id,
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc),
            "level": record.levelname,
            "event": record.event,
            "message": record.getMessage(),
            "fields": fields,
        }


def log_event(
    logger: logging.Logger,
    event: str,
    *,
    level: int = logging.INFO,
    **fields: Any,
) -> None:
    """Emit a structured lifecycle event.

    ``event`` is the machine-readable name (e.g. ``"run.worker_started"``); it
    is both the record message and an ``event`` column. ``fields`` (skipping
    ``None``) become structured columns. Field names that collide with a
    LogRecord attribute are prefixed with ``ctx_`` rather than crashing.
    """
    extra: dict[str, Any] = {"event": event}
    for key, value in fields.items():
        if value is None:
            continue
        extra["ctx_" + key if key in _RESERVED_RECORD_KEYS else key] = value
    logger.log(level, event, extra=extra)
