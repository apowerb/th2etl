from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Sequence

from th2etl.pipelines.pipeline import run_pipeline
from th2etl.configs.settings import get_settings
from th2etl.scheduler.helpers import start_scheduler_manager_from_database
from th2etl.storage import DatabaseStorage
from th2etl.session.session import spawn_background_job

logger = logging.getLogger(__name__)


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


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
    parser.add_argument(
        "--start-db-scheduler",
        action="store_true",
        help="Load scheduler definitions from the database and run the scheduler manager",
    )
    parser.add_argument(
        "--scheduler-names",
        nargs="+",
        default=None,
        help="Optional list of scheduler names to load from the database",
    )
    parser.add_argument("--run-pipeline", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.run_pipeline:
        run_pipeline()
        return 0

    if args.background:
        extra_env = parse_env_vars(args.env)
        if args.start_db_scheduler:
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

        process = spawn_background_job("th2etl.runner", ["--run-pipeline"], extra_env=extra_env)
        print(f"Started isolated background job with PID {process.pid}")
        return 0

    if args.env:
        env_values = parse_env_vars(args.env)
        print("Running with these environment overrides:")
        for key, value in env_values.items():
            print(f"  {key}={value}")
        os.environ.update(env_values)

    if args.start_db_scheduler:
        settings = get_settings()
        with DatabaseStorage.from_settings(settings) as storage:
            start_scheduler_manager_from_database(
                storage,
                scheduler_names=args.scheduler_names,
            )
        return 0

    run_pipeline()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
