from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Sequence
import multiprocessing

import uvicorn

from th2etl.configs.settings import get_settings
from th2etl.scheduler.helpers import start_scheduler_manager_from_database
from th2etl.storage import DatabaseStorage
from th2etl.session.session import spawn_background_job
from th2etl.main import app
from th2etl.configs.logger import setup_logging


logger = logging.getLogger(__name__)


def parse_env_vars(env_vars: Sequence[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in env_vars:
        if "=" not in item:
            raise ValueError(f"Invalid environment variable format: {item}. Use KEY=VALUE.")
        key, _, value = item.partition("=")
        result[key] = value
    return result


def run_api_server(host: str, port: int) -> None:
    """Helper function to run the uvicorn server."""
    uvicorn.run(app, host=host, port=port)

def run_scheduler(scheduler_names: list[str] | None) -> None:
    """Helper function to run the scheduler."""
    settings = get_settings()
    with DatabaseStorage.from_settings(settings) as storage:
        start_scheduler_manager_from_database(
            storage,
            scheduler_names=scheduler_names,
        )

def main() -> int:
    setup_logging()

    parser = argparse.ArgumentParser(description="th2etl ETL runner")
    parser.add_argument("--background", action="store_true", help="Run the services in a separate isolated session")
    parser.add_argument(
        "--env",
        action="append",
        default=[],
        help="Additional environment variables for isolated session, use KEY=VALUE",
    )
    parser.add_argument(
        "--run-scheduler",
        action="store_true",
        help="Run the scheduler manager.",
    )
    parser.add_argument(
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
    
    args = parser.parse_args()

    if args.background:
        extra_env = parse_env_vars(args.env)
        command_args = []
        if args.serve_api:
            command_args.extend(["--serve-api", f"--host={args.host}", f"--port={args.port}"])
        if args.run_scheduler:
            command_args.append("--run-scheduler")
            if args.scheduler_names:
                command_args.extend(["--scheduler-names", *args.scheduler_names])
        
        if not command_args: # Default to running both in background
            command_args.extend(["--serve-api", "--run-scheduler"])

        process = spawn_background_job("th2etl.runner", command_args, extra_env=extra_env)
        print(f"Started isolated background services with PID {process.pid}")
        return 0

    if args.env:
        env_values = parse_env_vars(args.env)
        print("Running with these environment overrides:")
        for key, value in env_values.items():
            print(f"  {key}={value}")
        os.environ.update(env_values)

    # If no specific service is requested, run both.
    run_api = args.serve_api
    run_sch = args.run_scheduler
    if not run_api and not run_sch:
        run_api = True
        run_sch = True

    processes = []
    if run_api:
        api_process = multiprocessing.Process(target=run_api_server, args=(args.host, args.port))
        processes.append(api_process)
        api_process.start()

    if run_sch:
        scheduler_process = multiprocessing.Process(target=run_scheduler, args=(args.scheduler_names,))
        processes.append(scheduler_process)
        scheduler_process.start()

    for p in processes:
        p.join()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
