from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Sequence

from ..pipelines.pipeline import run_pipeline
from .session import spawn_background_job

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
    parser.add_argument("--background", action="store_true", help="Run the pipeline in a separate isolated session")
    parser.add_argument(
        "--env",
        action="append",
        default=[],
        help="Additional environment variables for isolated session, use KEY=VALUE",
    )
    parser.add_argument("--run-pipeline", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.run_pipeline:
        run_pipeline()
        return 0

    if args.background:
        extra_env = parse_env_vars(args.env)
        process = spawn_background_job("th2etl.runner", ["--run-pipeline"], extra_env=extra_env)
        print(f"Started isolated background job with PID {process.pid}")
        return 0

    if args.env:
        env_values = parse_env_vars(args.env)
        print("Running pipeline with these environment overrides:")
        for key, value in env_values.items():
            print(f"  {key}={value}")
        os.environ.update(env_values)

    run_pipeline()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
