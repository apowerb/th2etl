from __future__ import annotations

import logging
from collections import deque
from typing import Any, Sequence

from ..blocs import ExporterBloc, LoaderBloc, TransformerBloc
from ..blocs.base import Bloc

logger = logging.getLogger(__name__)


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

    def execute(self) -> dict[str, Any]:
        logger.info("Starting pipeline execution")
        context: dict[str, Any] = {}
        for bloc in self._resolve_execution_order():
            logger.info("Running bloc %s (%s)", bloc.name, bloc.type.value)
            bloc.execute(context)
        logger.info("Pipeline execution completed")
        return context


class ExampleLoader(LoaderBloc):
    def __init__(self) -> None:
        super().__init__(name="example_loader")

    def execute(self, context: dict[str, Any]) -> None:
        logger.info("Loading rows")
        context["raw_rows"] = [
            {"id": 1, "value": 100},
            {"id": 2, "value": 200},
        ]
        logger.info("Loaded %d rows", len(context["raw_rows"]))


class ExampleTransformer(TransformerBloc):
    def __init__(self) -> None:
        super().__init__(name="example_transformer", dependencies=["example_loader"])

    def execute(self, context: dict[str, Any]) -> None:
        raw_rows = context.get("raw_rows", [])
        logger.info("Transforming %d rows", len(raw_rows))
        transformed = [{"id": row["id"], "value": row["value"] * 2} for row in raw_rows]
        context["transformed_rows"] = transformed
        logger.info("Transformed %d rows", len(transformed))


class ExampleExporter(ExporterBloc):
    def __init__(self) -> None:
        super().__init__(name="example_exporter", dependencies=["example_transformer"])

    def execute(self, context: dict[str, Any]) -> None:
        exported_rows = context.get("transformed_rows", [])
        logger.info("Exporting %d rows", len(exported_rows))
        for row in exported_rows:
            logger.info("Exported row: %s", row)
        context["exported_count"] = len(exported_rows)


def build_example_pipeline() -> Pipeline:
    return Pipeline([ExampleLoader(), ExampleTransformer(), ExampleExporter()])


def run_pipeline() -> None:
    pipeline = build_example_pipeline()
    pipeline.execute()
