from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any

from th2etl.configs.settings import get_settings
from th2etl.configs.run_logging import bind_run_context, log_event, reset_run_context
from th2etl.pipelines.context import RunContext
from th2etl.pipelines.pipeline import build_pipeline_from_database
from th2etl.storage.database import DatabaseStorage, RunStatus

logger = logging.getLogger(__name__)


def execute_pipeline_run(
    run_id: int,
    pipeline_name: str,
    variables: dict[str, Any] | None = None,
) -> None:
    """Execute a pipeline ad-hoc and record its outcome.

    Designed to run as a FastAPI BackgroundTask: it opens its own storage
    connection (the request-scoped one is already closed), drives the run
    through RUNNING -> SUCCESS/FAILED, and persists the result/error so the
    run can be polled via GET /pipelines/{name}/runs/{run_id}.

    The whole body is wrapped so that a crash BEFORE the storage connection
    opens (e.g. settings/DB unreachable) still emits ``run.worker_failed_early``
    instead of leaving the run silently ``pending`` with no trace (blind
    spots #1/#2: the background task never reached the DB).
    """
    token = bind_run_context(run_id=run_id, pipeline=pipeline_name, source="api")
    started = time.monotonic()
    # The very first line proves the background task actually started — its
    # absence in the log is the signature of a run stuck 'pending'.
    log_event(logger, "run.worker_started", run_id=run_id, pipeline=pipeline_name)
    try:
        settings = get_settings()
        with DatabaseStorage.from_settings(settings) as storage:
            storage.update_pipeline_run(
                run_id,
                status=RunStatus.RUNNING.value,
                started_at=datetime.utcnow().isoformat(),
            )
            try:
                pipeline = build_pipeline_from_database(storage, pipeline_name)
                run_context = RunContext(
                    scheduler_name=pipeline_name,
                    context_vars=dict(variables or {}),
                )
                pipeline.execute(run_context)
            except Exception as exc:  # noqa: BLE001 - record any failure for polling
                logger.exception("Pipeline run %s (%s) failed", run_id, pipeline_name)
                storage.update_pipeline_run(
                    run_id,
                    status=RunStatus.FAILED.value,
                    error=str(exc),
                    finished_at=datetime.utcnow().isoformat(),
                )
                log_event(
                    logger,
                    "run.worker_failed",
                    level=logging.ERROR,
                    run_id=run_id,
                    error=str(exc),
                    duration_ms=round((time.monotonic() - started) * 1000),
                )
                return

            storage.update_pipeline_run(
                run_id,
                status=RunStatus.SUCCESS.value,
                finished_at=datetime.utcnow().isoformat(),
            )
            log_event(
                logger,
                "run.worker_succeeded",
                run_id=run_id,
                duration_ms=round((time.monotonic() - started) * 1000),
            )
    except Exception as exc:  # noqa: BLE001 - the run may be stuck 'pending'
        logger.exception("Pipeline run %s (%s) crashed before completion", run_id, pipeline_name)
        log_event(
            logger,
            "run.worker_failed_early",
            level=logging.ERROR,
            run_id=run_id,
            error=str(exc),
            duration_ms=round((time.monotonic() - started) * 1000),
        )
        raise
    finally:
        reset_run_context(token)
