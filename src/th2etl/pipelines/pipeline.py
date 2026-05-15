from __future__ import annotations

import logging
from collections import deque
from typing import Any, Callable, Sequence
from datetime import datetime
from pathlib import Path
import json

from th2etl.blocs import (
    ExporterBloc,
    LoaderBloc,
    TransformerBloc,
    CsvLoaderBloc,
    PostgresLoaderBloc,
    ApiLoaderBloc,
)
from th2etl.blocs.base import Bloc
from th2etl.storage import DatabaseStorage
from th2etl.blocs.schemas import ExampleTransformerConfig, ExampleExporterConfig
from th2etl.pipelines.context import RunContext

logger = logging.getLogger(__name__)

BlocFactory = Callable[[str, dict[str, Any], Sequence[str] | None], Bloc]
BLOC_FACTORY_REGISTRY: dict[str, BlocFactory] = {}


def register_bloc_factory(bloc_type: str, factory: BlocFactory) -> None:
    BLOC_FACTORY_REGISTRY[bloc_type] = factory


def build_bloc_from_record(name: str, bloc_type: str, dependencies: Sequence[str] | None, config: dict[str, Any] | None) -> Bloc:
    factory = BLOC_FACTORY_REGISTRY.get(bloc_type)
    if factory is None:
        raise ValueError(f"No registered bloc factory for bloc_type={bloc_type!r}")
    return factory(name, config or {}, dependencies)


def build_pipeline_from_database(storage: DatabaseStorage, pipeline_name: str) -> "Pipeline":
    pipeline_record = storage.get_pipeline(pipeline_name)
    if pipeline_record is None:
        raise ValueError(f"Pipeline {pipeline_name!r} does not exist")

    blocs: list[Bloc] = []
    for bloc_name in pipeline_record.bloc_names:
        bloc_record = storage.get_bloc(bloc_name)
        if bloc_record is None:
            raise ValueError(f"Bloc {bloc_name!r} referenced by pipeline {pipeline_name!r} does not exist")
        bloc = build_bloc_from_record(
            bloc_record.name,
            bloc_record.bloc_type,
            bloc_record.dependencies,
            bloc_record.config,
        )
        blocs.append(bloc)

    return Pipeline(blocs)


class Pipeline:
    def __init__(self, blocs: Sequence[Bloc] | None = None) -> None:
        self.blocs: dict[str, Bloc] = {}
        if blocs:
            for bloc in blocs:
                self.add_bloc(bloc)

    def add_bloc(self, bloc: Bloc) -> None:
        if bloc.name in self.blocs:
            raise ValueError(f"A bloc named {bloc.name!r} is already registered.")
        self.blocs[bloc.name] = bloc

    def _resolve_execution_order(self) -> list[Bloc]:
        incoming: dict[str, int] = {name: 0 for name in self.blocs}
        outbound: dict[str, set[str]] = {name: set() for name in self.blocs}

        for bloc in self.blocs.values():
            for dependency in bloc.dependencies:
                if dependency not in self.blocs:
                    raise ValueError(f"Dependency {dependency!r} for bloc {bloc.name!r} is not registered.")
                outbound[dependency].add(bloc.name)
                incoming[bloc.name] += 1

        queue = deque(name for name, count in incoming.items() if count == 0)
        order: list[Bloc] = []

        while queue:
            name = queue.popleft()
            order.append(self.blocs[name])
            for child_name in outbound[name]:
                incoming[child_name] -= 1
                if incoming[child_name] == 0:
                    queue.append(child_name)

        if len(order) != len(self.blocs):
            missing = sorted(name for name, count in incoming.items() if count > 0)
            raise ValueError(f"Detected a cycle or unresolved dependencies: {missing}")

        return order

    def execute(self, run_context: RunContext | None = None) -> RunContext:
        if run_context is None:
            run_context = RunContext()
        
        execution_id = f" for '{run_context.scheduler_name}'" if run_context.scheduler_name else ""
        logger.info("Starting pipeline execution%s", execution_id)

        # Ensure output directory exists if provided
        if run_context.output_dir:
            run_context.output_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Using output directory: {run_context.output_dir}")

        for bloc in self._resolve_execution_order():
            logger.info("Running bloc %s (%s)", bloc.name, bloc.type.value)
            bloc.execute(run_context)
            
        logger.info("Pipeline execution completed%s", execution_id)
        return run_context


class ExampleTransformer(TransformerBloc):
    def __init__(self, name: str = "example_transformer", dependencies: Sequence[str] | None = None, config: dict[str, Any] | None = None) -> None:
        super().__init__(name=name, dependencies=dependencies)
        self.config = ExampleTransformerConfig(**(config or {}))

    def execute(self, run_context: RunContext) -> None:
        # This example assumes a single data source from the context
        input_data = next(iter(run_context.context_vars.values()), [])
        logger.debug("Transforming %d rows", len(input_data))

        transformed = [
            {"id": row.get("id"), "value": float(row.get("value", 0)) * self.config.factor}
            for row in input_data
        ]
        run_context.context_vars[f"{self.name}_data"] = transformed
        logger.debug("Transformed %d rows", len(transformed))


class ExampleExporter(ExporterBloc):
    def __init__(self, name: str = "example_exporter", dependencies: Sequence[str] | None = None, config: dict[str, Any] | None = None) -> None:
        super().__init__(name=name, dependencies=dependencies)
        self.config = ExampleExporterConfig(**(config or {}))

    def execute(self, run_context: RunContext) -> None:
        # This example assumes a single data source from the context
        exported_rows = next(iter(run_context.context_vars.values()), [])
        logger.debug("Exporting %d rows", len(exported_rows))

        if run_context.output_dir:
            output_file = run_context.output_dir / "exported_data.json"
            with output_file.open("w") as f:
                json.dump(exported_rows, f, indent=2)
            logger.debug(f"Saved {len(exported_rows)} rows to {output_file}")
        else:
            logger.warning("No output directory set. Skipping file export.")

        run_context.context_vars["exported_count"] = len(exported_rows)


def _csv_loader_factory(name: str, config: dict[str, Any], dependencies: Sequence[str] | None) -> Bloc:
    return CsvLoaderBloc(name=name, dependencies=dependencies, config=config)


def _postgres_loader_factory(name: str, config: dict[str, Any], dependencies: Sequence[str] | None) -> Bloc:
    return PostgresLoaderBloc(name=name, dependencies=dependencies, config=config)


def _api_loader_factory(name: str, config: dict[str, Any], dependencies: Sequence[str] | None) -> Bloc:
    return ApiLoaderBloc(name=name, dependencies=dependencies, config=config)


def _example_transformer_factory(name: str, config: dict[str, Any], dependencies: Sequence[str] | None) -> Bloc:
    return ExampleTransformer(name=name, dependencies=dependencies, config=config)


def _example_exporter_factory(name: str, config: dict[str, Any], dependencies: Sequence[str] | None) -> Bloc:
    return ExampleExporter(name=name, dependencies=dependencies, config=config)


register_bloc_factory("csv_loader", _csv_loader_factory)
register_bloc_factory("postgres_loader", _postgres_loader_factory)
register_bloc_factory("api_loader", _api_loader_factory)
register_bloc_factory("example_transformer", _example_transformer_factory)
register_bloc_factory("example_exporter", _example_exporter_factory)


def build_example_pipeline() -> Pipeline:
    # This function is now for demonstration and may not be used directly by the scheduler
    # if all pipelines are defined in the database.
    transformer = ExampleTransformer(dependencies=["my_csv_loader"])
    exporter = ExampleExporter(dependencies=["my_transformer"])
    loader = CsvLoaderBloc(name="my_csv_loader", config={"file_path": "path/to/your/data.csv"})
    return Pipeline([loader, transformer, exporter])


def run_pipeline() -> None:
    pipeline = build_example_pipeline()
    pipeline.execute()
