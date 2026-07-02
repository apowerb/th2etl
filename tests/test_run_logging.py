"""Structured run-logging primitives: ambient context, JSON formatter, and
propagation into worker threads via contextvars.copy_context()."""
from __future__ import annotations

import contextvars
import json
import logging
import threading

from th2etl.configs.run_logging import (
    EventOnlyFilter,
    JsonFormatter,
    RunContextFilter,
    bind_run_context,
    get_run_context,
    log_event,
    reset_run_context,
)


def _record(msg: str = "hello", **extra) -> logging.LogRecord:
    rec = logging.makeLogRecord({"name": "th2etl.test", "levelname": "INFO", "levelno": logging.INFO, "msg": msg})
    for k, v in extra.items():
        setattr(rec, k, v)
    return rec


def test_json_formatter_emits_valid_json_with_envelope():
    line = JsonFormatter().format(_record("started"))
    obj = json.loads(line)
    assert obj["message"] == "started"
    assert obj["level"] == "INFO"
    assert obj["logger"] == "th2etl.test"
    assert obj["ts"].endswith("+00:00")


def test_json_formatter_surfaces_extra_fields():
    obj = json.loads(JsonFormatter().format(_record(run_id=7, status="running", duration_ms=12)))
    assert obj["run_id"] == 7
    assert obj["status"] == "running"
    assert obj["duration_ms"] == 12


def test_bind_and_reset_run_context_is_scoped():
    assert get_run_context() == {}
    token = bind_run_context(run_id=1, pipeline="p", ignored=None)
    try:
        ctx = get_run_context()
        assert ctx == {"run_id": 1, "pipeline": "p"}  # None skipped
    finally:
        reset_run_context(token)
    assert get_run_context() == {}


def test_filter_injects_context_but_extra_wins():
    token = bind_run_context(run_id=1, pipeline="ambient")
    try:
        rec = _record(pipeline="explicit")  # explicit extra present on record
        assert RunContextFilter().filter(rec) is True
        assert rec.run_id == 1            # injected from context
        assert rec.pipeline == "explicit"  # not overridden
    finally:
        reset_run_context(token)


def test_log_event_sets_event_and_fields(caplog):
    logger = logging.getLogger("th2etl.test.event")
    with caplog.at_level(logging.INFO, logger="th2etl.test.event"):
        log_event(logger, "run.worker_started", run_id=5, source="api", nothing=None)
    rec = caplog.records[-1]
    assert rec.message == "run.worker_started"
    assert rec.event == "run.worker_started"
    assert rec.run_id == 5
    assert rec.source == "api"
    assert not hasattr(rec, "nothing")  # None skipped


def test_log_event_renames_reserved_field_names(caplog):
    """A field named like a LogRecord attribute (e.g. 'module') must not crash
    logging — it is prefixed with ctx_ instead of raising KeyError."""
    logger = logging.getLogger("th2etl.test.reserved")
    with caplog.at_level(logging.INFO, logger="th2etl.test.reserved"):
        log_event(logger, "some.event", module="db", run_id=3)  # 'module' is reserved
    rec = caplog.records[-1]
    assert rec.ctx_module == "db"
    assert rec.run_id == 3
    assert rec.module != "db"  # the real LogRecord.module is untouched


def test_event_only_filter_passes_only_event_records():
    f = EventOnlyFilter()
    evt = _record("run.created")
    evt.event = "run.created"
    assert f.filter(evt) is True
    assert f.filter(_record("plain uvicorn line")) is False  # no 'event' attr


def test_context_propagates_to_thread_via_copy_context():
    """A bloc running in a worker thread must see the run context — but only if
    the thread is started through a copied context (the mechanism Pipeline uses)."""
    token = bind_run_context(run_id=99)
    try:
        seen: dict = {}

        def worker():
            seen.update(get_run_context())

        ctx = contextvars.copy_context()
        t = threading.Thread(target=lambda: ctx.run(worker))
        t.start()
        t.join()
        assert seen == {"run_id": 99}
    finally:
        reset_run_context(token)


def test_plain_thread_does_NOT_inherit_context():
    """Guards the regression: a plain thread (no copy_context) sees an empty
    context — this is exactly why Pipeline.execute must copy the context."""
    token = bind_run_context(run_id=1)
    try:
        seen: dict = {"sentinel": True}

        def worker():
            seen.clear()
            seen.update(get_run_context())

        t = threading.Thread(target=worker)
        t.start()
        t.join()
        assert seen == {}
    finally:
        reset_run_context(token)
