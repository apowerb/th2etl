from .pipelines.pipeline import run_pipeline
from .scheduler.helpers import CronScheduler, CronTrigger, schedule_pipeline
from .session.runner import main
from .storage import DatabaseStorage


def hello() -> str:
    return "Hello from th2etl!"
