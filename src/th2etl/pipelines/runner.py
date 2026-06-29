from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from th2etl.configs.settings import get_settings
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
    """
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
            return

        storage.update_pipeline_run(
            run_id,
            status=RunStatus.SUCCESS.value,
            finished_at=datetime.utcnow().isoformat(),
        )
