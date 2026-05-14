from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from typing import Iterable

from th2etl.pipelines.pipeline import Pipeline

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
        logger.info("Running scheduled pipeline %s at %s", self.name, datetime.now())
        self.pipeline.execute()
        self._next_run = self.trigger.next_run(datetime.now())

    def run_pending(self) -> bool:
        now = datetime.now().replace(second=0, microsecond=0)
        if now >= self._next_run:
            self.run_once()
            return True
        return False

    def start(self, interval_seconds: int = 30) -> None:
        logger.info("Starting scheduler %s with next run at %s", self.name, self._next_run)
        try:
            while True:
                if self.run_pending():
                    logger.info("Scheduled run completed, next run at %s", self._next_run)
                time.sleep(interval_seconds)
        except KeyboardInterrupt:
            logger.info("Scheduler %s stopped by keyboard interrupt", self.name)


def schedule_pipeline(pipeline: Pipeline, expression: str) -> CronScheduler:
    trigger = CronTrigger(expression)
    return CronScheduler(pipeline=pipeline, trigger=trigger)
