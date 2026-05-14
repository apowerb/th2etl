from __future__ import annotations

import logging
import time
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Iterable, Sequence

from th2etl.pipelines.pipeline import Pipeline, build_pipeline_from_database
from th2etl.storage import DatabaseStorage

logger = logging.getLogger(__name__)

FIELD_RANGES = {
    "minute": (0, 59),
    "hour": (0, 23),
    "day": (1, 31),
    "month": (1, 12),
    "weekday": (0, 6),
}


def _parse_part(part: str, min_value: int, max_value: int) -> set[int]:
    values: set[int] = set()
    if part == "*":
        return set(range(min_value, max_value + 1))

    for token in part.split(","):
        if "/" in token:
            range_part, step_part = token.split("/", 1)
            step = int(step_part)
        else:
            range_part = token
            step = 1

        if range_part == "*":
            start, end = min_value, max_value
        elif "-" in range_part:
            start_str, end_str = range_part.split("-", 1)
            start = int(start_str)
            end = int(end_str)
        else:
            start = int(range_part)
            end = start

        if start < min_value or end > max_value:
            raise ValueError(f"Cron value {start}-{end} is out of range {min_value}-{max_value}")

        values.update(range(start, end + 1, step))

    return values


class CronTrigger:
    def __init__(self, expression: str) -> None:
        fields = expression.strip().split()
        if len(fields) != 5:
            raise ValueError("Cron expression must have 5 fields: minute hour day month weekday")

        self.minute = _parse_part(fields[0], *FIELD_RANGES["minute"])
        self.hour = _parse_part(fields[1], *FIELD_RANGES["hour"])
        self.day = _parse_part(fields[2], *FIELD_RANGES["day"])
        self.month = _parse_part(fields[3], *FIELD_RANGES["month"])
        self.weekday = _parse_part(fields[4], *FIELD_RANGES["weekday"])

    def matches(self, dt: datetime) -> bool:
        return (
            dt.minute in self.minute
            and dt.hour in self.hour
            and dt.day in self.day
            and dt.month in self.month
            and dt.weekday() in self.weekday
        )

    def next_run(self, after: datetime | None = None) -> datetime:
        current = after or datetime.now()
        current = current.replace(second=0, microsecond=0)
        if self.matches(current):
            return current

        search = current + timedelta(minutes=1)
        while True:
            if self.matches(search):
                return search
            search += timedelta(minutes=1)


class CronScheduler:
    def __init__(self, pipeline: Pipeline, trigger: CronTrigger, name: str | None = None) -> None:
        self.pipeline = pipeline
        self.trigger = trigger
        self.name = name or pipeline.__class__.__name__
        self._next_run = self.trigger.next_run(datetime.now())

    def run_once(self) -> None:
        start_at = datetime.now()
        logger.info("Running scheduled pipeline %s at %s", self.name, start_at)
        self.pipeline.execute()
        self._next_run = self.trigger.next_run(start_at + timedelta(minutes=1))

    def run_pending(self) -> bool:
        now = datetime.now().replace(second=0, microsecond=0)
        if now >= self._next_run:
            self.run_once()
            return True
        return False

    def schedule_next_run(self, after: datetime | None = None) -> None:
        base = (after or datetime.now()).replace(second=0, microsecond=0) + timedelta(minutes=1)
        self._next_run = self.trigger.next_run(base)

    def next_run(self) -> datetime:
        return self._next_run

    def start(self, interval_seconds: int = 30) -> None:
        logger.info("Starting scheduler %s with next run at %s", self.name, self._next_run)
        try:
            while True:
                if self.run_pending():
                    logger.info("Scheduled run completed, next run at %s", self._next_run)
                time.sleep(interval_seconds)
        except KeyboardInterrupt:
            logger.info("Scheduler %s stopped by keyboard interrupt", self.name)


class SchedulerManager:
    def __init__(self, schedulers: Sequence[CronScheduler] | None = None, max_workers: int = 5, check_interval_seconds: int = 30) -> None:
        self.schedulers: list[CronScheduler] = list(schedulers or [])
        self.check_interval_seconds = check_interval_seconds
        self.executor = ThreadPoolExecutor(max_workers=max_workers)

    def add_scheduler(self, scheduler: CronScheduler) -> None:
        self.schedulers.append(scheduler)

    def run_pending(self) -> list[Future[None]]:
        now = datetime.now().replace(second=0, microsecond=0)
        futures: list[Future[None]] = []
        for scheduler in self.schedulers:
            if scheduler.next_run() <= now:
                logger.info("Dispatching scheduled pipeline %s for execution", scheduler.name)
                scheduler.schedule_next_run(now)
                futures.append(self.executor.submit(scheduler.run_once))
        return futures

    def start(self) -> None:
        logger.info("Starting SchedulerManager with %d pipelines", len(self.schedulers))
        try:
            while True:
                futures = self.run_pending()
                if futures:
                    logger.info("Dispatched %d scheduled pipeline(s)", len(futures))
                time.sleep(self.check_interval_seconds)
        except KeyboardInterrupt:
            logger.info("SchedulerManager stopped by keyboard interrupt")
        finally:
            self.executor.shutdown(wait=True)


def load_scheduler_manager(
    storage: DatabaseStorage,
    scheduler_names: Sequence[str] | None = None,
    max_workers: int = 5,
    check_interval_seconds: int = 30,
) -> SchedulerManager:
    manager = SchedulerManager(max_workers=max_workers, check_interval_seconds=check_interval_seconds)
    for scheduler in storage.list_schedulers():
        if scheduler_names and scheduler.name not in scheduler_names:
            continue

        trigger_record = storage.get_trigger(scheduler.trigger_name)
        if trigger_record is None:
            raise ValueError(f"Trigger {scheduler.trigger_name!r} referenced by scheduler {scheduler.name!r} does not exist")

        pipeline = build_pipeline_from_database(storage, scheduler.pipeline_name)
        manager.add_scheduler(
            CronScheduler(
                pipeline=pipeline,
                trigger=CronTrigger(trigger_record.cron_expression),
                name=scheduler.name,
            )
        )

    return manager


def start_scheduler_manager_from_database(
    storage: DatabaseStorage,
    scheduler_names: Sequence[str] | None = None,
    max_workers: int = 5,
    check_interval_seconds: int = 30,
) -> None:
    """Load schedulers from the database and start the manager loop."""
    manager = load_scheduler_manager(
        storage,
        scheduler_names=scheduler_names,
        max_workers=max_workers,
        check_interval_seconds=check_interval_seconds,
    )
    manager.start()


def schedule_pipeline(pipeline: Pipeline, expression: str) -> CronScheduler:
    trigger = CronTrigger(expression)
    return CronScheduler(pipeline=pipeline, trigger=trigger)
