from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Sequence

import uvicorn

from th2etl.pipelines.pipeline import run_pipeline
from th2etl.configs.settings import get_settings
from th2etl.scheduler.helpers import start_scheduler_manager_from_database
from th2etl.storage import DatabaseStorage
from th2etl.session.session import spawn_background_job
from th2etl.main import app

logger = logging.getLogger(__name__)


def configure_logging() -> None:
    # Default log level from environment, fallback to INFO
    default_level = os.environ.get("TH2ETL_LOG_LEVEL", "INFO").upper()
    
    # Basic config sets the root logger level and format
    logging.basicConfig(
        level=default_level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Allow fine-grained log levels from a comma-separated environment variable
    # Example: TH2ETL_LOG_LEVELS=th2etl.scheduler:INFO,th2etl:WARNING
    log_levels_str = os.environ.get("TH2ETL_LOG_LEVELS")
    if log_levels_str:
        for logger_config in log_levels_str.split(","):
            if ":" in logger_config:
                logger_name, level_name = logger_config.split(":", 1)
                level = logging.getLevelName(level_name.upper())
                if isinstance(level, int):
                    logging.getLogger(logger_name.strip()).setLevel(level)
                else:
                    logging.warning(f"Invalid log level '{level_name}' for logger '{logger_name.strip()}'")


def parse_env_vars(env_vars: Sequence[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in env_vars:
        if "=" not in item:
            raise ValueError(f"Invalid environment variable format: {item}. Use KEY=VALUE.")
        key, _, value = item.partition("=")
        result[key] = value
    return result


def main() -> int:
    configure_logging()

    parser = argparse.ArgumentParser(description="th2etl ETL runner")
    parser.add_argument("--background", action="store_true", help="Run the pipeline or scheduler in a separate isolated session")
    parser.add_argument(
        "--env",
        action="append",
        default=[],
        help="Additional environment variables for isolated session, use KEY=VALUE",
    )

    # Use a mutually exclusive group for commands
    command_group = parser.add_mutually_exclusive_group()
    command_group.add_argument(
        "--start-db-scheduler",
        action="store_true",
        help="Load scheduler definitions from the database and run the scheduler manager (default action).",
    )
    command_group.add_argument(
        "--serve-api",
        action="store_true",
        help="Run the FastAPI server.",
    )

    # Scheduler-specific arguments
    scheduler_group = parser.add_argument_group("Scheduler options")
    scheduler_group.add_argument(
        "--scheduler-names",
        nargs="+",
        default=None,
        help="Optional list of scheduler names to load from the database",
    )

    # API-specific arguments
    api_group = parser.add_argument_group("API server options")
    api_group.add_argument("--host", default="0.0.0.0", help="Host for the API server.")
    api_group.add_argument("--port", default=8000, type=int, help="Port for the API server.")
    
    parser.add_argument("--run-pipeline", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.run_pipeline:
        run_pipeline()
        return 0

    if args.background:
        extra_env = parse_env_vars(args.env)
        if args.serve_api:
            command_args = ["--serve-api", f"--host={args.host}", f"--port={args.port}"]
            process = spawn_background_job("th2etl.runner", command_args, extra_env=extra_env)
            print(f"Started isolated background API server with PID {process.pid}")
        else:  # Default for background is the scheduler
            command_args = ["--start-db-scheduler"]
            if args.scheduler_names:
                command_args += ["--scheduler-names", *args.scheduler_names]
            process = spawn_background_job(
                "th2etl.runner",
                command_args,
                extra_env=extra_env,
            )
            print(f"Started isolated background DB scheduler with PID {process.pid}")
        return 0

    if args.env:
        env_values = parse_env_vars(args.env)
        print("Running with these environment overrides:")
        for key, value in env_values.items():
            print(f"  {key}={value}")
        os.environ.update(env_values)

    if args.serve_api:
        uvicorn.run(app, host=args.host, port=args.port)
        return 0

    # Default action is to start the scheduler
    settings = get_settings()
    with DatabaseStorage.from_settings(settings) as storage:
        start_scheduler_manager_from_database(
            storage,
            scheduler_names=args.scheduler_names,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
