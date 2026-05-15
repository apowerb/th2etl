from __future__ import annotations

import logging
import csv
import json
from typing import Any, Sequence

import psycopg
import requests
from psycopg.rows import dict_row

from th2etl.blocs.base import LoaderBloc
from th2etl.pipelines.context import RunContext
from th2etl.configs.settings import get_settings
from th2etl.blocs.schemas import CsvLoaderConfig, PostgresLoaderConfig, ApiLoaderConfig

logger = logging.getLogger(__name__)


class CsvLoaderBloc(LoaderBloc):
    """Loads data from a CSV file."""

    def __init__(
        self,
        name: str,
        dependencies: Sequence[str] | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(name=name, dependencies=dependencies)
        self.config = CsvLoaderConfig(**(config or {}))

    def execute(self, run_context: RunContext) -> None:
        logger.info(f"Loading data from CSV file: {self.config.file_path}")
        try:
            with open(self.config.file_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f, delimiter=self.config.delimiter)
                rows = list(reader)
            run_context.context_vars[f"{self.name}_data"] = rows
            logger.info(f"Loaded {len(rows)} rows from {self.config.file_path}")
        except FileNotFoundError:
            logger.error(f"CSV file not found at: {self.config.file_path}")
            raise
        except Exception as e:
            logger.error(f"Failed to load data from {self.config.file_path}: {e}")
            raise


class PostgresLoaderBloc(LoaderBloc):
    """Loads data from a PostgreSQL database."""

    def __init__(
        self,
        name: str,
        dependencies: Sequence[str] | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(name=name, dependencies=dependencies)
        self.config = PostgresLoaderConfig(**(config or {}))
        self.settings = get_settings()

    def execute(self, run_context: RunContext) -> None:
        logger.info("Executing query against PostgreSQL database")
        try:
            with psycopg.connect(self.settings.database_dsn, row_factory=dict_row) as conn:
                with conn.cursor() as cur:
                    cur.execute(self.config.query)
                    rows = cur.fetchall()
            
            # Convert all values to strings for consistent downstream processing
            rows = [{k: str(v) for k, v in row.items()} for row in rows]
            
            run_context.context_vars[f"{self.name}_data"] = rows
            logger.info(f"Loaded {len(rows)} rows from the database")
        except Exception as e:
            logger.error(f"Failed to execute query: {e}")
            raise


class ApiLoaderBloc(LoaderBloc):
    """Loads data from a web API."""

    def __init__(
        self,
        name: str,
        dependencies: Sequence[str] | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(name=name, dependencies=dependencies)
        self.config = ApiLoaderConfig(**(config or {}))

    def execute(self, run_context: RunContext) -> None:
        logger.info(f"Fetching data from API: {self.config.method} {self.config.url}")
        try:
            response = requests.request(
                self.config.method,
                self.config.url,
                params=self.config.params,
                headers=self.config.headers,
                json=self.config.json_payload,
            )
            response.raise_for_status()
            data = response.json()
            
            if not isinstance(data, list):
                logger.warning("API response is not a list, wrapping it in a list.")
                data = [data]
            
            run_context.context_vars[f"{self.name}_data"] = data
            logger.info(f"Loaded {len(data)} records from API")
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch data from API: {e}")
            raise
