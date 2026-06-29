from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import pandas as pd
from sqlalchemy import create_engine

from th2etl.blocs.base import ExporterBloc, LoaderBloc
from th2etl.blocs.schemas import PostgresLoaderConfig, PostgresExporterConfig
from th2etl.configs.settings import get_settings

if TYPE_CHECKING:
    from th2etl.pipelines.context import RunContext

logger = logging.getLogger(__name__)


class PostgresLoaderBloc(LoaderBloc):
    """Loads data from PostgreSQL into the run context.

    Writes ``context_vars["{name}_data"]`` as a list of row dicts, matching
    the other loader blocs.
    """

    def __init__(self, name: str, config: dict[str, Any] | None = None) -> None:
        super().__init__(name=name)
        self.config = PostgresLoaderConfig(**(config or {}))

    def execute(self, run_context: "RunContext") -> None:
        logger.info("Executing PostgresLoaderBloc: %s", self.name)
        engine = create_engine(get_settings().database_dsn)
        with engine.connect() as connection:
            df = pd.read_sql(self.config.query, connection)
        run_context.context_vars[f"{self.name}_data"] = df.to_dict(orient="records")
        logger.info("Loaded %d rows in PostgresLoaderBloc: %s", len(df), self.name)


class PostgresExporterBloc(ExporterBloc):
    """Exports a source bloc's data (``context_vars["{source_bloc}_data"]``)
    to a PostgreSQL table."""

    def __init__(self, name: str, config: dict[str, Any] | None = None) -> None:
        super().__init__(name=name)
        self.config = PostgresExporterConfig(**(config or {}))

    def execute(self, run_context: "RunContext") -> None:
        logger.info("Executing PostgresExporterBloc: %s", self.name)
        data = run_context.context_vars.get(f"{self.config.source_bloc}_data")
        if data is None:
            raise ValueError(f"No data found for source bloc: {self.config.source_bloc}")

        df = pd.DataFrame(data)
        engine = create_engine(get_settings().database_dsn)
        with engine.connect() as connection:
            df.to_sql(
                self.config.table_name,
                connection,
                schema=self.config.schema,
                if_exists=self.config.if_exists,
                index=False,
            )
        logger.info("Exported %d rows in PostgresExporterBloc: %s", len(df), self.name)
