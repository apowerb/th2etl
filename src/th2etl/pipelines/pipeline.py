from __future__ import annotations

import logging
from collections import deque
from typing import Any, Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from th2etl.blocs import ExporterBloc, LoaderBloc, TransformerBloc
from th2etl.blocs.base import Bloc
from th2etl.storage import DatabaseStorage

logger = logging.getLogger(__name__)

BlocFactory = Callable[[str, dict[str, Any], Sequence[str] | None], Bloc]
BLOC_FACTORY_REGISTRY: dict[str, BlocFactory] = {}


@dataclass
class RunContext:
    """Provides details about the current pipeline run."""

    scheduler_name: str | None = None
    trigger_name: str | None = None
    scheduled_at: datetime | None = None
    output_dir: Path | None = None

    # Arbitrary storage for passing data between blocs
    context_vars: dict[str, Any] = field(default_factory=dict)


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
        logger.info("Starting pipeline execution")

        # If no context is provided, create a default one
        if run_context is None:
            run_context = RunContext()

        # Ensure output directory exists if provided
        if run_context.output_dir:
            run_context.output_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Using output directory: {run_context.output_dir}")

        for bloc in self._resolve_execution_order():
            logger.info("Running bloc %s (%s)", bloc.name, bloc.type.value)
            bloc.execute(run_context.context_vars)

        logger.info("Pipeline execution completed")
        return run_context


class ExampleLoader(LoaderBloc):
    def __init__(self, name: str = "example_loader", dependencies: Sequence[str] | None = None, config: dict[str, Any] | None = None) -> None:
        super().__init__(name=name, dependencies=dependencies)
        self.config = config or {}

    def execute(self, context: dict[str, Any]) -> None:
        logger.info("Loading rows")
        context["raw_rows"] = [
            {"id": 1, "value": 100},
            {"id": 2, "value": 200},
        ]
        logger.info("Loaded %d rows", len(context["raw_rows"]))


class ExampleTransformer(TransformerBloc):
    def __init__(self, name: str = "example_transformer", dependencies: Sequence[str] | None = None, config: dict[str, Any] | None = None) -> None:
        super().__init__(name=name, dependencies=dependencies)
        self.config = config or {}

    def execute(self, context: dict[str, Any]) -> None:
        raw_rows = context.get("raw_rows", [])
        logger.info("Transforming %d rows", len(raw_rows))
        transformed = [{"id": row["id"], "value": row["value"] * 2} for row in raw_rows]
        context["transformed_rows"] = transformed
        logger.info("Transformed %d rows", len(transformed))


class ExampleExporter(ExporterBloc):
    def __init__(self, name: str = "example_exporter", dependencies: Sequence[str] | None = None, config: dict[str, Any] | None = None) -> None:
        super().__init__(name=name, dependencies=dependencies)
        self.config = config or {}

    def execute(self, context: dict[str, Any]) -> None:
        exported_rows = context.get("transformed_rows", [])
        logger.info("Exporting %d rows", len(exported_rows))

        # The run_context is not directly available here, so we can't easily get the output_dir
        # This part of the example would need to be updated if it needs to write to a file
        for row in exported_rows:
            logger.info("Exported row: %s", row)
        context["exported_count"] = len(exported_rows)


def _example_loader_factory(name: str, config: dict[str, Any], dependencies: Sequence[str] | None) -> Bloc:
    return ExampleLoader(name=name, dependencies=dependencies, config=config)


def _example_transformer_factory(name: str, config: dict[str, Any], dependencies: Sequence[str] | None) -> Bloc:
    return ExampleTransformer(name=name, dependencies=dependencies, config=config)


def _example_exporter_factory(name: str, config: dict[str, Any], dependencies: Sequence[str] | None) -> Bloc:
    return ExampleExporter(name=name, dependencies=dependencies, config=config)


register_bloc_factory("example_loader", _example_loader_factory)
register_bloc_factory("example_transformer", _example_transformer_factory)
register_bloc_factory("example_exporter", _example_exporter_factory)


def build_example_pipeline() -> Pipeline:
    return Pipeline([ExampleLoader(), ExampleTransformer(), ExampleExporter()])


def run_pipeline() -> None:
    pipeline = build_example_pipeline()
    pipeline.execute()
