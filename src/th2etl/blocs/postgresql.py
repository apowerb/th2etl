from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import pandas as pd
from sqlalchemy import create_engine

from th2etl.blocs.base import ExporterBloc, LoaderBloc

if TYPE_CHECKING:
    from th2etl.pipelines.context import RunContext

logger = logging.getLogger(__name__)


class PostgresLoaderBloc(LoaderBloc):
    """
    A bloc that loads data from a PostgreSQL table into the run context.
    """

    def __init__(
        self,
        name: str,
        table_name: str,
        schema: str | None = None,
    ) -> None:
        super().__init__(name)
        self.table_name = table_name
        self.schema = schema

    def execute(self, run_context: RunContext) -> None:
        """
        Loads data from the specified PostgreSQL table and adds it to the run context.
        """
        logger.info(f"Executing PostgresLoaderBloc: {self.name}")
        db_settings = run_context.get_database_settings()
        engine = create_engine(db_settings.database_dsn)
        query = f"SELECT * FROM {self.schema}.{self.table_name}" if self.schema else f"SELECT * FROM {self.table_name}"
        
        with engine.connect() as connection:
            df = pd.read_sql(query, connection)
            run_context.set_data(self.name, df)
        
        logger.info(f"Finished executing PostgresLoaderBloc: {self.name}")


class PostgresExporterBloc(ExporterBloc):
    """
    A bloc that exports data from the run context to a PostgreSQL table.
    """

    def __init__(
        self,
        name: str,
        table_name: str,
        source_bloc: str,
        schema: str | None = None,
        if_exists: str = "replace",
    ) -> None:
        super().__init__(name)
        self.table_name = table_name
        self.source_bloc = source_bloc
        self.schema = schema
        self.if_exists = if_exists

    def execute(self, run_context: RunContext) -> None:
        """
        Exports data from a dependency to the specified PostgreSQL table.
        """
        logger.info(f"Executing PostgresExporterBloc: {self.name}")
        db_settings = run_context.get_database_settings()
        engine = create_engine(db_settings.database_dsn)
        
        df = run_context.get_data(self.source_bloc)
        
        if df is None:
            raise ValueError(f"No data found for source bloc: {self.source_bloc}")
            
        with engine.connect() as connection:
            df.to_sql(
                self.table_name,
                connection,
                schema=self.schema,
                if_exists=self.if_exists,
                index=False,
            )
        
        logger.info(f"Finished executing PostgresExporterBloc: {self.name}")
