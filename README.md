# th2etl
thaink2 in house built ETL and automatisation library

## Design

A pipeline is modeled as a set of interdependent blocs. Each bloc is one of:

- `LoaderBloc` — loads or extracts raw data
- `TransformerBloc` — transforms data between stages
- `ExporterBloc` — exports or writes output

Dependencies between blocs are resolved before execution, so the pipeline runs in dependency order.

## Usage

Run the pipeline in the current process:

```bash
python -m th2etl.runner
```

Run the pipeline in a separate isolated session:

```bash
python -m th2etl.runner --background
```

Pass environment variables into the isolated session:

```bash
python -m th2etl.runner --background --env SOURCE=prod --env DESTINATION=warehouse
```

If the package is installed, use the CLI entry point:

```bash
th2etl --background --env SOURCE=prod
```

## Persistent Storage

Use `DatabaseStorage` to persist bloc, pipeline, trigger, and scheduler definitions.

```python
from th2etl import DatabaseStorage
from th2etl.configs.settings import get_settings

settings = get_settings()
with DatabaseStorage.from_settings(settings) as storage:
    storage.create_bloc("loader1", "loader", dependencies=[], config={"source": "csv"})
    storage.create_trigger("every_hour", "0 * * * *")
    storage.create_pipeline("example_pipeline", ["loader1"])
    storage.create_scheduler("example_scheduler", "example_pipeline", "every_hour")

    print(storage.list_pipelines())
    print(storage.list_schedulers())
```

The `Settings` object reads database connection details from environment variables such as `DATABASE_HOST`, `DATABASE_PORT`, `DATABASE_NAME`, `DATABASE_USER`, `DATABASE_PASSWORD`, and optionally `DATABASE_SSL_MODE`. You can also provide `DATABASE_URL` directly.

## Scheduler

Use `CronTrigger` and `CronScheduler` to run a pipeline on a cron-like schedule:

```python
from th2etl.pipelines import build_example_pipeline
from th2etl.scheduler import CronScheduler, CronTrigger

pipeline = build_example_pipeline()
trigger = CronTrigger("*/5 * * * *")
scheduler = CronScheduler(pipeline, trigger)
scheduler.start()
```

Or create a scheduler helper directly:

```python
from th2etl.pipelines import build_example_pipeline
from th2etl.scheduler import schedule_pipeline

pipeline = build_example_pipeline()
scheduler = schedule_pipeline(pipeline, "0 * * * *")
scheduler.start()
```
