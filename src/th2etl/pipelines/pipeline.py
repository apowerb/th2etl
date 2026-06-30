from __future__ import annotations

import logging
from typing import Any, Callable, Sequence
import json
import concurrent.futures

from th2etl.blocs import (
    ExporterBloc,
    TransformerBloc,
    CsvLoaderBloc,
    PostgresLoaderBloc,
    PostgresExporterBloc,
    ApiLoaderBloc,
    PdfLoaderBloc,
    RunAdkAgentsBloc,
    RunAdkFromJwtBloc,
    RefreshWebhooksBloc,
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


def build_bloc_from_record(name: str, bloc_type: str, config: dict[str, Any] | None) -> Bloc:
    factory = BLOC_FACTORY_REGISTRY.get(bloc_type)
    if factory is None:
        raise ValueError(f"No registered bloc factory for bloc_type={bloc_type!r}")
    return factory(name, config or {})


def build_pipeline_from_database(storage: DatabaseStorage, pipeline_name: str) -> "Pipeline":
    pipeline_record = storage.get_pipeline(pipeline_name)
    if pipeline_record is None:
        raise ValueError(f"Pipeline {pipeline_name!r} does not exist")

    all_blocs: dict[str, Bloc] = {}
    for stage in pipeline_record.stages:
        for bloc_name in stage:
            if bloc_name in all_blocs:
                continue
            bloc_record = storage.get_bloc(bloc_name)
            if bloc_record is None:
                raise ValueError(f"Bloc {bloc_name!r} referenced by pipeline {pipeline_name!r} does not exist")
            bloc = build_bloc_from_record(
                bloc_record.name,
                bloc_record.bloc_type,
                bloc_record.config,
            )
            all_blocs[bloc.name] = bloc

    return Pipeline(pipeline_record.stages, list(all_blocs.values()))


class Pipeline:
    def __init__(self, stages: list[list[str]], blocs: Sequence[Bloc] | None = None) -> None:
        self.stages = stages
        self.blocs: dict[str, Bloc] = {}
        if blocs:
            for bloc in blocs:
                self.add_bloc(bloc)

    def add_bloc(self, bloc: Bloc) -> None:
        if bloc.name in self.blocs:
            raise ValueError(f"A bloc named {bloc.name!r} is already registered.")
        self.blocs[bloc.name] = bloc

    def execute(self, run_context: RunContext | None = None) -> RunContext:
        if run_context is None:
            run_context = RunContext()
        
        execution_id = f" for '{run_context.scheduler_name}'" if run_context.scheduler_name else ""
        logger.info("Starting pipeline execution%s", execution_id)

        # Ensure output directory exists if provided
        if run_context.output_dir:
            run_context.output_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Using output directory: {run_context.output_dir}")

        for i, stage in enumerate(self.stages):
            logger.info(f"Executing stage {i + 1}/{len(self.stages)}")
            with concurrent.futures.ThreadPoolExecutor() as executor:
                futures = []
                for bloc_name in stage:
                    bloc = self.blocs.get(bloc_name)
                    if bloc is None:
                        raise ValueError(f"Bloc {bloc_name!r} not found in pipeline.")
                    
                    logger.info("Submitting bloc %s (%s) for execution", bloc.name, bloc.type.value)
                    futures.append(executor.submit(bloc.execute, run_context))
                
                # Wait for all blocs in the current stage to complete
                for future in concurrent.futures.as_completed(futures):
                    try:
                        future.result()  # Raise any exceptions from the bloc execution
                    except Exception as e:
                        logger.error(f"An error occurred during bloc execution: {e}")
                        # Depending on desired behavior, you might want to cancel other futures
                        # and stop the pipeline execution here.
                        raise

            logger.info(f"Stage {i + 1} completed.")
            
        logger.info("Pipeline execution completed%s", execution_id)
        return run_context


class ExampleTransformer(TransformerBloc):
    def __init__(self, name: str = "example_transformer", config: dict[str, Any] | None = None) -> None:
        super().__init__(name=name)
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
    def __init__(self, name: str = "example_exporter", config: dict[str, Any] | None = None) -> None:
        super().__init__(name=name)
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


def _csv_loader_factory(name: str, config: dict[str, Any]) -> Bloc:
    return CsvLoaderBloc(name=name, config=config)


def _postgres_loader_factory(name: str, config: dict[str, Any]) -> Bloc:
    return PostgresLoaderBloc(name=name, config=config)


def _postgres_exporter_factory(name: str, config: dict[str, Any]) -> Bloc:
    return PostgresExporterBloc(name=name, config=config)


def _api_loader_factory(name: str, config: dict[str, Any]) -> Bloc:
    return ApiLoaderBloc(name=name, config=config)


def _pdf_loader_factory(name: str, config: dict[str, Any]) -> Bloc:
    return PdfLoaderBloc(name=name, config=config)


def _example_transformer_factory(name: str, config: dict[str, Any]) -> Bloc:
    return ExampleTransformer(name=name, config=config)


def _example_exporter_factory(name: str, config: dict[str, Any]) -> Bloc:
    return ExampleExporter(name=name, config=config)


def _run_adk_agents_factory(name: str, config: dict[str, Any]) -> Bloc:
    return RunAdkAgentsBloc(name=name, config=config)


def _run_adk_from_jwt_factory(name: str, config: dict[str, Any]) -> Bloc:
    return RunAdkFromJwtBloc(name=name, config=config)


def _refresh_webhooks_factory(name: str, config: dict[str, Any]) -> Bloc:
    return RefreshWebhooksBloc(name=name, config=config)


register_bloc_factory("csv_loader", _csv_loader_factory)
register_bloc_factory("postgres_loader", _postgres_loader_factory)
register_bloc_factory("postgres_exporter", _postgres_exporter_factory)
register_bloc_factory("api_loader", _api_loader_factory)
register_bloc_factory("pdf_loader", _pdf_loader_factory)
register_bloc_factory("example_transformer", _example_transformer_factory)
register_bloc_factory("example_exporter", _example_exporter_factory)
register_bloc_factory("run_adk_agents", _run_adk_agents_factory)
register_bloc_factory("run_adk_from_jwt", _run_adk_from_jwt_factory)
register_bloc_factory("refresh_webhooks", _refresh_webhooks_factory)


def build_example_pipeline() -> Pipeline:
    # This function is now for demonstration and may not be used directly by the scheduler
    # if all pipelines are defined in the database.
    loader = CsvLoaderBloc(name="my_csv_loader", config={"file_path": "path/to/your/data.csv"})
    transformer = ExampleTransformer(name="my_transformer")
    exporter = ExampleExporter(name="my_exporter")
    
    stages = [
        ["my_csv_loader"],
        ["my_transformer"],
        ["my_exporter"],
    ]
    
    return Pipeline(stages, [loader, transformer, exporter])


def run_pipeline() -> None:
    pipeline = build_example_pipeline()
    pipeline.execute()
