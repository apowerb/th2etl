from __future__ import annotations

import logging
import sys
from pathlib import Path

from th2etl.configs.settings import get_settings
from th2etl.configs.run_logging import (
    EventOnlyFilter,
    JsonFormatter,
    RunContextFilter,
    RunLogHandler,
)

# A list of the main modules to create separate log files for
LOGGING_MODULES = [
    "th2etl.scheduler",
    "th2etl.api",
    "th2etl.pipelines",
    "th2etl.storage",
    "th2etl.blocs",
]

def setup_logging():
    """Configures logging to separate files for each main module."""
    settings = get_settings()
    log_format = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
    formatter = logging.Formatter(log_format, datefmt="%Y-%m-%d %H:%M:%S")

    # Injects the ambient run context (run_id/pipeline/...) onto every record so
    # both text and JSON handlers can surface it, including from worker threads.
    run_context_filter = RunContextFilter()

    # A single JSON handler streams every run-lifecycle event as one object per
    # line. Shared across root + module loggers (module loggers set
    # propagate=False, so they need the handler attached directly).
    json_handler = None
    if settings.run_log_json and settings.log_dir:
        Path(settings.log_dir).mkdir(parents=True, exist_ok=True)
        json_handler = logging.FileHandler(Path(settings.log_dir) / settings.run_log_file)
        json_handler.setFormatter(JsonFormatter())
        json_handler.addFilter(run_context_filter)
        # Keep runs.jsonl a pure structured-event stream: only records emitted
        # via log_event() (carrying an 'event' attr) — no third-party or
        # free-text logs (which may embed response bodies/tokens).
        json_handler.addFilter(EventOnlyFilter())

    # A DB handler persists the same structured events to a queryable table so a
    # run's flow can be fetched per-run via the API. It reuses RunContextFilter
    # (for run_id) and only persists records carrying a run_id (guard is inside
    # RunLogHandler.emit). Building it opens a dedicated DB connection; if that
    # fails at startup we degrade gracefully to file-only logging rather than
    # breaking the app.
    run_log_handler = None
    if settings.run_log_db:
        try:
            from th2etl.storage.run_log_writer import RunLogWriter

            writer = RunLogWriter(settings.database_dsn, schema=settings.database_schema)
            run_log_handler = RunLogHandler(writer.write)
            run_log_handler.addFilter(run_context_filter)
        except Exception as exc:  # noqa: BLE001 - never let logging setup crash boot
            logging.getLogger(__name__).warning(
                "Run-log DB persistence disabled (writer init failed): %s", exc
            )
            run_log_handler = None

    # --- Root logger for console output ---
    root_logger = logging.getLogger()
    # Clear any existing handlers to avoid duplicates
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    stream_handler.addFilter(run_context_filter)
    root_logger.addHandler(stream_handler)
    if json_handler is not None:
        root_logger.addHandler(json_handler)
    if run_log_handler is not None:
        root_logger.addHandler(run_log_handler)

    # --- File-based logging ---
    if settings.log_dir:
        log_dir = Path(settings.log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        print(f"Logging to directory: {log_dir}")

        # General log file for all messages
        main_log_file = log_dir / "th2etl.log"
        main_file_handler = logging.FileHandler(main_log_file)
        main_file_handler.setFormatter(formatter)
        main_file_handler.addFilter(run_context_filter)
        root_logger.addHandler(main_file_handler)

        # Create separate log files for each main module
        for module_name in LOGGING_MODULES:
            module_logger = logging.getLogger(module_name)
            # Clear first so a second setup_logging() call (tests, dev reload)
            # does not accumulate duplicate handlers -> duplicate JSON lines.
            module_logger.handlers.clear()
            log_file = log_dir / f"{module_name.split('.')[-1]}.log"
            file_handler = logging.FileHandler(log_file)
            file_handler.setFormatter(formatter)
            file_handler.addFilter(run_context_filter)
            module_logger.addHandler(file_handler)
            if json_handler is not None:
                module_logger.addHandler(json_handler)
            if run_log_handler is not None:
                module_logger.addHandler(run_log_handler)
            module_logger.propagate = False # Prevents messages from going to the root logger's file handler

    # --- Set log levels ---
    default_level = settings.log_level.upper()
    root_logger.setLevel(default_level)

    log_levels_str = settings.log_levels
    if log_levels_str:
        for logger_config in log_levels_str.split(","):
            if ":" in logger_config:
                logger_name, level_name = logger_config.split(":", 1)
                level = logging.getLevelName(level_name.upper())
                if isinstance(level, int):
                    logging.getLogger(logger_name.strip()).setLevel(level)
                else:
                    logging.warning(f"Invalid log level '{level_name}' for logger '{logger_name.strip()}'")
