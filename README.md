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

To start the database-backed scheduler manager directly from the command line:

```bash
th2etl --start-db-scheduler
```

Or in the background:

```bash
th2etl --start-db-scheduler --background
```

## Quickstart

Create pipeline metadata from the command line and then start the ETL service.

1. Set your PostgreSQL database settings in environment variables:

```powershell
$env:DATABASE_HOST = "localhost"
$env:DATABASE_PORT = "5432"
$env:DATABASE_NAME = "th2etl"
$env:DATABASE_USER = "etl_user"
$env:DATABASE_PASSWORD = "secret"
```

2. Create blocs in the database:

```powershell
python -c "from th2etl import DatabaseStorage; from th2etl.configs.settings import get_settings; s = get_settings();
with DatabaseStorage.from_settings(s) as storage:
    storage.create_bloc('example_loader','example_loader',dependencies=[],config={'source':'csv'})
    storage.create_bloc('example_transformer','example_transformer',dependencies=['example_loader'],config={'factor':2})
    storage.create_bloc('example_exporter','example_exporter',dependencies=['example_transformer'],config={'destination':'stdout'})"
```

3. Create a trigger for your pipeline:

```powershell
python -c "from th2etl import DatabaseStorage; from th2etl.configs.settings import get_settings; s = get_settings();
with DatabaseStorage.from_settings(s) as storage:
    storage.create_trigger('every_hour','0 * * * *')"
```

4. Create the pipeline and optional scheduler:

```powershell
python -c "from th2etl import DatabaseStorage; from th2etl.configs.settings import get_settings; s = get_settings();
with DatabaseStorage.from_settings(s) as storage:
    storage.create_pipeline('example_pipeline',['example_loader','example_transformer','example_exporter'])
    storage.create_scheduler('example_scheduler','example_pipeline','every_hour')"
```

5. Start the ETL service in the background:

```bash
python -m th2etl.runner --background
```

Or if the package is installed, run:

```bash
th2etl --background
```

## Persistent Storage

Use `DatabaseStorage` to persist bloc, pipeline, trigger, and scheduler definitions.

```python
from th2etl import DatabaseStorage
from th2etl.configs.settings import get_settings

settings = get_settings()
with DatabaseStorage.from_settings(settings) as storage:
    storage.create_bloc("example_loader", "example_loader", dependencies=[], config={"source": "csv"})
    storage.create_bloc("example_transformer", "example_transformer", dependencies=["example_loader"], config={"factor": 2})
    storage.create_bloc("example_exporter", "example_exporter", dependencies=["example_transformer"], config={"destination": "stdout"})
    storage.create_trigger("every_hour", "0 * * * *")
    storage.create_pipeline("example_pipeline", ["example_loader", "example_transformer", "example_exporter"])
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

For multiple pipelines with independent trigger schedules, use `SchedulerManager` so each pipeline can run on its own cadence in parallel:

```python
from th2etl.pipelines import build_example_pipeline
from th2etl.scheduler import CronTrigger, CronScheduler, SchedulerManager

pipeline1 = build_example_pipeline()
pipeline2 = build_example_pipeline()

scheduler1 = CronScheduler(pipeline1, CronTrigger("0 * * * *"), name="hourly_pipeline")
scheduler2 = CronScheduler(pipeline2, CronTrigger("*/5 * * * *"), name="five_minute_pipeline")

manager = SchedulerManager([scheduler1, scheduler2])
manager.start()
```

If you persist scheduler metadata in the database, load scheduled pipelines dynamically from `DatabaseStorage`:

```python
from th2etl import DatabaseStorage
from th2etl.configs.settings import get_settings
from th2etl.scheduler import load_scheduler_manager

settings = get_settings()
with DatabaseStorage.from_settings(settings) as storage:
    manager = load_scheduler_manager(storage)
    manager.start()
```

Or create a scheduler helper directly:

```python
from th2etl.pipelines import build_example_pipeline
from th2etl.scheduler import schedule_pipeline

pipeline = build_example_pipeline()
scheduler = schedule_pipeline(pipeline, "0 * * * *")
scheduler.start()
```
