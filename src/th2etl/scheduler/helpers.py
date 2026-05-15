from __future__ import annotations

import logging
import time
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Iterable, Sequence
from pathlib import Path

from th2etl.pipelines.pipeline import Pipeline, RunContext, build_pipeline_from_database
from th2etl.storage import DatabaseStorage, TriggerRecord
from th2etl.configs.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

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
        token = token.strip()
        if not token:
            raise ValueError(f"Invalid cron syntax: empty token in '{part}'")

        if "/" in token:
            range_part, step_part = token.split("/", 1)
            if not step_part:
                raise ValueError(f"Invalid cron syntax: missing step value in '{token}'")
            try:
                step = int(step_part)
            except ValueError as exc:
                raise ValueError(f"Invalid cron step in '{token}': {exc}") from exc
        else:
            range_part = token
            step = 1

        if not range_part:
            raise ValueError(f"Invalid cron syntax: missing range before '/' in '{token}'")

        if range_part == "*":
            start, end = min_value, max_value
        elif "-" in range_part:
            start_str, end_str = range_part.split("-", 1)
            try:
                start = int(start_str)
                end = int(end_str)
            except ValueError as exc:
                raise ValueError(f"Invalid cron range in '{token}': {exc}") from exc
        else:
            try:
                start = int(range_part)
            except ValueError as exc:
                raise ValueError(f"Invalid cron value in '{token}': {exc}") from exc
            end = start

        if start < min_value or end > max_value:
            raise ValueError(f"Cron value {start}-{end} is out of range {min_value}-{max_value}")

        values.update(range(start, end + 1, step))

    return values


class CronTrigger:
    def __init__(self, expression: str) -> None:
        self.expression = expression
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
    def __init__(self, pipeline: Pipeline, trigger: CronTrigger, name: str | None = None, trigger_name: str | None = None, settings: Settings | None = None) -> None:
        self.pipeline = pipeline
        self.trigger = trigger
        self.trigger_name = trigger_name
        self.name = name or pipeline.__class__.__name__
        self.settings = settings
        self._next_run = self.trigger.next_run(datetime.now())
        logger.info(f"Initialized scheduler '{self.name}' with trigger '{trigger.expression}'. Next run at {self._next_run}")

    def run_once(self) -> None:
        start_at = datetime.now()
        logger.info("Executing scheduled pipeline '%s'", self.name)
        
        output_dir: Path | None = None
        if self.settings and self.settings.pipelines_logs_dir:
            run_timestamp = start_at.strftime("%Y%m%d_%H%M%S")
            output_dir = self.settings.pipelines_logs_dir / self.name / run_timestamp
        
        run_context = RunContext(
            scheduler_name=self.name,
            trigger_name=self.trigger_name,
            scheduled_at=start_at,
            output_dir=output_dir,
        )

        try:
            self.pipeline.execute(run_context)
            duration = (datetime.now() - start_at).total_seconds()
            logger.info("Successfully finished pipeline '%s' in %.2f seconds", self.name, duration)
        except Exception:
            duration = (datetime.now() - start_at).total_seconds()
            logger.exception("Pipeline '%s' failed after %.2f seconds", self.name, duration)
        finally:
            # Always schedule the next run, even if the pipeline failed
            self._next_run = self.trigger.next_run(start_at + timedelta(minutes=1))

    def run_pending(self) -> bool:
        now = datetime.now().replace(second=0, microsecond=0)
        logger.debug(f"Checking scheduler '{self.name}' at {now}. Next run is at {self._next_run}.")
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
    def __init__(self, schedulers: Sequence[CronScheduler] | None = None, max_workers: int = 5, check_interval_seconds: int = 30, storage: DatabaseStorage | None = None, refresh_interval_seconds: int = 60, settings: Settings | None = None) -> None:
        self.schedulers: list[CronScheduler] = list(schedulers or [])
        self.check_interval_seconds = check_interval_seconds
        self.refresh_interval_seconds = refresh_interval_seconds
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.storage = storage
        self.settings = settings
        self._last_triggers_refresh = datetime.min
        self._last_schedulers_refresh = datetime.min

    def add_scheduler(self, scheduler: CronScheduler) -> None:
        logger.info(f"Adding scheduler '{scheduler.name}' to manager.")
        self.schedulers.append(scheduler)

    def run_pending(self) -> list[Future[None]]:
        now = datetime.now().replace(second=0, microsecond=0)
        futures: list[Future[None]] = []
        for scheduler in self.schedulers:
            if scheduler.next_run() <= now:
                logger.info("Dispatching scheduled pipeline '%s' for execution", scheduler.name)
                scheduler.schedule_next_run(now)
                futures.append(self.executor.submit(scheduler.run_once))
        return futures

    def _on_trigger_change(self, trigger_record: TriggerRecord) -> None:
        for scheduler in self.schedulers:
            if scheduler.trigger_name != trigger_record.name:
                continue

            logger.info(
                "Refreshing scheduler '%s' because trigger '%s' changed to '%s'",
                scheduler.name,
                trigger_record.name,
                trigger_record.cron_expression,
            )
            try:
                scheduler.trigger = CronTrigger(trigger_record.cron_expression)
                scheduler.schedule_next_run(datetime.now())
            except ValueError as exc:
                logger.warning(
                    "Skipping invalid trigger update for %s: %s",
                    trigger_record.name,
                    exc,
                )

    def _refresh_or_add_scheduler(self, scheduler_record: SchedulerRecord) -> None:
        existing = next((s for s in self.schedulers if s.name == scheduler_record.name), None)
        if existing is not None:
            self._replace_scheduler(existing, scheduler_record)
            return

        try:
            scheduler = self._build_scheduler_from_record(scheduler_record)
        except Exception as exc:
            logger.warning("Failed to add scheduler %s from change event: %s", scheduler_record.name, exc)
            return

        self.schedulers.append(scheduler)
        logger.info("Added scheduler %s to manager", scheduler_record.name)

    def _replace_scheduler(self, existing: CronScheduler, scheduler_record: SchedulerRecord) -> None:
        try:
            new_scheduler = self._build_scheduler_from_record(scheduler_record)
        except Exception as exc:
            logger.warning("Failed to refresh scheduler '%s': %s", scheduler_record.name, exc)
            return

        logger.info("Updating existing scheduler '%s' with new settings", scheduler_record.name)
        existing.pipeline = new_scheduler.pipeline
        existing.trigger = new_scheduler.trigger
        existing.trigger_name = new_scheduler.trigger_name
        existing.schedule_next_run(datetime.now())

    def _build_scheduler_from_record(self, scheduler_record: SchedulerRecord) -> CronScheduler:
        trigger_record = self.storage.get_trigger(scheduler_record.trigger_name)
        if trigger_record is None:
            raise ValueError(
                f"Trigger {scheduler_record.trigger_name!r} referenced by scheduler {scheduler_record.name!r} does not exist"
            )

        pipeline = build_pipeline_from_database(self.storage, scheduler_record.pipeline_name)
        return CronScheduler(
            pipeline=pipeline,
            trigger=CronTrigger(trigger_record.cron_expression),
            name=scheduler_record.name,
            trigger_name=scheduler_record.trigger_name,
            settings=self.settings,
        )

    def _refresh_triggers_from_database(self) -> None:
        """Reload trigger cron expressions from database to pick up changes as fallback."""
        if not self.storage:
            return
        
        now = datetime.now()
        if (now - self._last_triggers_refresh).total_seconds() < self.refresh_interval_seconds:
            return
        
        try:
            for scheduler in self.schedulers:
                if not scheduler.trigger_name:
                    continue

                trigger_record = self.storage.get_trigger(scheduler.trigger_name)
                if not trigger_record:
                    continue

                new_cron = trigger_record.cron_expression
                if new_cron != scheduler.trigger.expression:
                    logger.info(
                        "Trigger %s cron expression changed from '%s' to '%s'",
                        scheduler.name,
                        scheduler.trigger.expression,
                        new_cron,
                    )
                    try:
                        scheduler.trigger = CronTrigger(new_cron)
                        scheduler.schedule_next_run(now)
                    except ValueError as exc:
                        logger.warning(
                            "Skipping invalid refreshed cron '%s' for trigger %s: %s",
                            new_cron,
                            scheduler.trigger_name,
                            exc,
                        )
            self._last_triggers_refresh = now
        except Exception as e:
            logger.warning("Failed to refresh triggers from database: %s", e)

    def _refresh_schedulers_from_database(self) -> None:
        if not self.storage:
            return

        now = datetime.now()
        if (now - self._last_schedulers_refresh).total_seconds() < self.refresh_interval_seconds:
            return

        try:
            db_schedulers = {record.name: record for record in self.storage.list_schedulers()}
            current_names = {scheduler.name for scheduler in self.schedulers}

            for record in db_schedulers.values():
                self._refresh_or_add_scheduler(record)

            removed_names = current_names - set(db_schedulers)
            if removed_names:
                self.schedulers = [s for s in self.schedulers if s.name not in removed_names]
                logger.info("Removed schedulers no longer present in DB: %s", sorted(removed_names))

            self._last_schedulers_refresh = now
        except Exception as e:
            logger.warning("Failed to refresh schedulers from database: %s", e)

    def start(self) -> None:
        logger.info("Starting SchedulerManager with %d pipelines", len(self.schedulers))
        if not self.schedulers:
            logger.warning("SchedulerManager started with no schedulers.")
        try:
            while True:
                logger.debug("SchedulerManager main loop tick.")
                self._refresh_triggers_from_database()
                self._refresh_schedulers_from_database()
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
    refresh_interval_seconds: int = 60,
    settings: Settings | None = None,
) -> SchedulerManager:
    logger.info("Loading scheduler manager from database.")
    manager = SchedulerManager(
        max_workers=max_workers,
        check_interval_seconds=check_interval_seconds,
        storage=storage,
        refresh_interval_seconds=refresh_interval_seconds,
        settings=settings,
    )
    if hasattr(storage, "add_trigger_change_listener"):
        storage.add_trigger_change_listener(manager._on_trigger_change)
    
    schedulers_from_db = storage.list_schedulers()
    logger.info(f"Found {len(schedulers_from_db)} scheduler(s) in the database.")

    for scheduler in schedulers_from_db:
        if scheduler_names and scheduler.name not in scheduler_names:
            continue

        trigger_record = storage.get_trigger(scheduler.trigger_name)
        if trigger_record is None:
            raise ValueError(f"Trigger {scheduler.trigger_name!r} referenced by scheduler {scheduler.name!r} does not exist")

        try:
            trigger = CronTrigger(trigger_record.cron_expression)
        except ValueError as exc:
            raise ValueError(
                f"Invalid cron expression for trigger {scheduler.trigger_name!r}: {exc}"
            ) from exc

        pipeline = build_pipeline_from_database(storage, scheduler.pipeline_name)
        manager.add_scheduler(
            CronScheduler(
                pipeline=pipeline,
                trigger=trigger,
                name=scheduler.name,
                trigger_name=scheduler.trigger_name,
                settings=settings,
            )
        )
    
    logger.info(f"SchedulerManager loaded with {len(manager.schedulers)} scheduler(s).")
    return manager


def start_scheduler_manager_from_database(
    storage: DatabaseStorage,
    scheduler_names: Sequence[str] | None = None,
    max_workers: int = 5,
    check_interval_seconds: int = 30,
    refresh_interval_seconds: int = 60,
) -> None:
    """Load schedulers from the database and start the manager loop.
    
    Triggers are refreshed from the database every refresh_interval_seconds to pick up changes.
    """
    manager = load_scheduler_manager(
        storage,
        scheduler_names=scheduler_names,
        max_workers=max_workers,
        check_interval_seconds=check_interval_seconds,
        refresh_interval_seconds=refresh_interval_seconds,
        settings=settings,
    )
    manager.start()


def schedule_pipeline(pipeline: Pipeline, expression: str) -> CronScheduler:
    trigger = CronTrigger(expression)
    return CronScheduler(pipeline=pipeline, trigger=trigger)
