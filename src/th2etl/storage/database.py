from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Callable

import psycopg
from psycopg.rows import dict_row

from th2etl.configs.settings import Settings

logger = logging.getLogger(__name__)

# How long a migration may wait for its ACCESS EXCLUSIVE lock before giving
# up. Short on purpose: while it waits, every later reader waits too.
MIGRATION_LOCK_TIMEOUT = "3s"


class RunStatus(str, Enum):
    """Lifecycle states of a pipeline run."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class BlocRecord:
    id: int | None
    name: str
    bloc_type: str
    dependencies: list[str]
    config: dict[str, Any]
    description: str | None
    created_at: str
    updated_at: str


@dataclass
class PipelineRecord:
    id: int | None
    name: str
    stages: list[list[str]]
    description: str | None
    created_at: str
    updated_at: str


@dataclass
class TriggerRecord:
    id: int | None
    name: str
    pipeline_id: int | None
    cron_expression: str
    description: str | None
    created_at: str
    updated_at: str


@dataclass
class SchedulerRecord:
    id: int | None
    name: str
    pipeline_name: str
    trigger_name: str
    description: str | None
    variables: dict[str, Any]
    active: bool
    created_at: str
    updated_at: str


@dataclass
class RunRecord:
    id: int | None
    pipeline_name: str
    status: str
    variables: dict[str, Any]
    result: dict[str, Any] | None
    error: str | None
    scheduler_name: str | None
    created_at: str
    updated_at: str
    started_at: str | None
    finished_at: str | None


class DatabaseStorage:
    def __init__(self, dsn: str | None = None, settings: Settings | None = None) -> None:
        if settings is not None:
            dsn = settings.database_dsn
            self.schema = settings.database_schema
        else:
            self.schema = None
        
        if not dsn:
            raise ValueError(
                "DatabaseStorage requires either a DSN or a Settings instance with database connection settings"
            )

        self.dsn = dsn
        self.connection = psycopg.connect(self.dsn, row_factory=dict_row)
        self._trigger_listeners: list[Callable[[TriggerRecord], None]] = []
        self._create_tables()

    @classmethod
    def from_settings(cls, settings: Settings) -> "DatabaseStorage":
        return cls(settings=settings)

    def _table_name(self, table: str) -> str:
        """Return schema-qualified table name with etl_ prefix if schema is set."""
        prefixed_table = f"etl_{table}"
        if self.schema:
            return f"{self.schema}.{prefixed_table}"
        return prefixed_table

    def add_trigger_change_listener(self, listener: Callable[[TriggerRecord], None]) -> None:
        self._trigger_listeners.append(listener)

    def remove_trigger_change_listener(self, listener: Callable[[TriggerRecord], None]) -> None:
        self._trigger_listeners.remove(listener)

    def _notify_trigger_change(self, trigger: TriggerRecord) -> None:
        for listener in list(self._trigger_listeners):
            try:
                listener(trigger)
            except Exception as exc:
                logger.warning("Trigger change listener failed: %s", exc)

    def check_connection(self) -> bool:
        """Checks if the database connection is active by executing a simple query."""
        try:
            self._query_one("SELECT 1")
            return True
        except Exception as e:
            logger.error(f"Database connection check failed: {e}")
            return False

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "DatabaseStorage":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def _create_tables(self) -> None:
        blocs_table = self._table_name("blocs")
        pipelines_table = self._table_name("pipelines")
        triggers_table = self._table_name("triggers")
        schedulers_table = self._table_name("schedulers")
        runs_table = self._table_name("pipeline_runs")
        runs_index = runs_table.replace(".", "_")

        with self.connection.cursor() as cur:
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {blocs_table} (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    bloc_type TEXT NOT NULL,
                    dependencies JSONB NOT NULL,
                    config JSONB NOT NULL,
                    description TEXT,
                    created_at TIMESTAMPTZ NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL
                );

                CREATE TABLE IF NOT EXISTS {pipelines_table} (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    stages JSONB NOT NULL,
                    description TEXT,
                    created_at TIMESTAMPTZ NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL
                );

                CREATE TABLE IF NOT EXISTS {triggers_table} (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    pipeline_id INTEGER NOT NULL REFERENCES {pipelines_table}(id) ON DELETE CASCADE,
                    cron_expression TEXT NOT NULL,
                    description TEXT,
                    created_at TIMESTAMPTZ NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL
                );

                CREATE TABLE IF NOT EXISTS {schedulers_table} (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    pipeline_id INTEGER NOT NULL REFERENCES {pipelines_table}(id) ON DELETE CASCADE,
                    trigger_id INTEGER NOT NULL REFERENCES {triggers_table}(id) ON DELETE CASCADE,
                    description TEXT,
                    variables JSONB NOT NULL DEFAULT '{{}}',
                    active BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at TIMESTAMPTZ NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL
                );

                CREATE TABLE IF NOT EXISTS {runs_table} (
                    id SERIAL PRIMARY KEY,
                    pipeline_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    variables JSONB NOT NULL,
                    result JSONB,
                    error TEXT,
                    scheduler_name TEXT,
                    created_at TIMESTAMPTZ NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL,
                    started_at TIMESTAMPTZ,
                    finished_at TIMESTAMPTZ
                );

                CREATE INDEX IF NOT EXISTS ix_{runs_index}_pipeline_name
                    ON {runs_table}(pipeline_name);
                """
            )
        self.connection.commit()
        self._apply_migrations(schedulers_table)

    # Run-once-per-process migrations. ALTER TABLE takes an ACCESS EXCLUSIVE
    # lock, so it must NOT run on every request — only once when the process
    # first opens a connection.
    _migrated: bool = False

    def _apply_migrations(self, schedulers_table: str) -> None:
        """Bring a pre-existing database up to the current column set.

        Every column added here is also declared in the CREATE TABLE above, so
        a fresh database is already correct and these statements are no-ops.
        They exist only for databases created before those columns landed.

        The wait for the lock is bounded, and that is the point. `ALTER TABLE
        ... ADD COLUMN IF NOT EXISTS` still takes an ACCESS EXCLUSIVE lock when
        the column is already there, and a request queued behind a long
        transaction blocks every reader that arrives after it — Postgres grants
        locks in order. On a database shared by several deployments that turns
        a no-op into a stall: seeding production on 2026-08-07 queued behind an
        idle-in-transaction session and froze `etl_schedulers` for ten minutes.

        Giving up costs a retry on the next boot. Waiting costs the database.
        """
        if DatabaseStorage._migrated:
            return
        runs_table = self._table_name("pipeline_runs")
        statements = (
            f"ALTER TABLE {schedulers_table} ADD COLUMN IF NOT EXISTS variables JSONB NOT NULL DEFAULT '{{}}'",
            f"ALTER TABLE {schedulers_table} ADD COLUMN IF NOT EXISTS active BOOLEAN NOT NULL DEFAULT TRUE",
            f"ALTER TABLE {runs_table} ADD COLUMN IF NOT EXISTS scheduler_name TEXT",
        )
        try:
            with self.connection.cursor() as cur:
                cur.execute(f"SET LOCAL lock_timeout = '{MIGRATION_LOCK_TIMEOUT}'")
                for statement in statements:
                    cur.execute(statement)
        except psycopg.errors.LockNotAvailable:
            self.connection.rollback()
            logger.warning(
                "th2etl: column migrations skipped, no table lock within %s. A "
                "fresh database already carries these columns from CREATE "
                "TABLE; a legacy one retries on the next boot. Nothing is "
                "blocked in the meantime.",
                MIGRATION_LOCK_TIMEOUT,
            )
            return
        self.connection.commit()
        DatabaseStorage._migrated = True

    def _now(self) -> str:
        return datetime.utcnow().isoformat()

    def _serialize(self, value: Any) -> str:
        return json.dumps(value)

    def _deserialize(self, value: str) -> Any:
        return json.loads(value)

    def _row_to_bloc(self, row: dict[str, Any]) -> BlocRecord:
        return BlocRecord(
            id=row["id"],
            name=row["name"],
            bloc_type=row["bloc_type"],
            dependencies=row["dependencies"],
            config=row["config"],
            description=row["description"],
            created_at=row["created_at"].isoformat() if row["created_at"] else "",
            updated_at=row["updated_at"].isoformat() if row["updated_at"] else "",
        )

    def _row_to_pipeline(self, row: dict[str, Any]) -> PipelineRecord:
        return PipelineRecord(
            id=row["id"],
            name=row["name"],
            stages=row["stages"],
            description=row["description"],
            created_at=row["created_at"].isoformat() if row["created_at"] else "",
            updated_at=row["updated_at"].isoformat() if row["updated_at"] else "",
        )

    def _row_to_trigger(self, row: dict[str, Any]) -> TriggerRecord:
        return TriggerRecord(
            id=row["id"],
            name=row["name"],
            pipeline_id=row.get("pipeline_id"),
            cron_expression=row["cron_expression"],
            description=row["description"],
            created_at=row["created_at"].isoformat() if row["created_at"] else "",
            updated_at=row["updated_at"].isoformat() if row["updated_at"] else "",
        )

    def _row_to_scheduler(self, row: dict[str, Any]) -> SchedulerRecord:
        pipelines_table = self._table_name("pipelines")
        triggers_table = self._table_name("triggers")
        pipeline_row = self._query_one(f"SELECT name FROM {pipelines_table} WHERE id = %s", (row["pipeline_id"],))
        if pipeline_row is None:
            raise ValueError(
                f"Scheduler {row['name']!r} references missing pipeline id {row['pipeline_id']!r}"
            )

        trigger_row = self._query_one(f"SELECT name FROM {triggers_table} WHERE id = %s", (row["trigger_id"],))
        if trigger_row is None:
            raise ValueError(
                f"Scheduler {row['name']!r} references missing trigger id {row['trigger_id']!r}"
            )

        return SchedulerRecord(
            id=row["id"],
            name=row["name"],
            pipeline_name=pipeline_row["name"],
            trigger_name=trigger_row["name"],
            description=row["description"],
            variables=row.get("variables") or {},
            active=row.get("active", True),
            created_at=row["created_at"].isoformat() if row["created_at"] else "",
            updated_at=row["updated_at"].isoformat() if row["updated_at"] else "",
        )

    def _row_to_run(self, row: dict[str, Any]) -> RunRecord:
        return RunRecord(
            id=row["id"],
            pipeline_name=row["pipeline_name"],
            status=row["status"],
            variables=row["variables"],
            result=row["result"],
            error=row["error"],
            scheduler_name=row.get("scheduler_name"),
            created_at=row["created_at"].isoformat() if row["created_at"] else "",
            updated_at=row["updated_at"].isoformat() if row["updated_at"] else "",
            started_at=row["started_at"].isoformat() if row["started_at"] else None,
            finished_at=row["finished_at"].isoformat() if row["finished_at"] else None,
        )

    def create_pipeline_run(
        self,
        pipeline_name: str,
        variables: dict[str, Any] | None = None,
        scheduler_name: str | None = None,
    ) -> RunRecord:
        now = self._now()
        runs_table = self._table_name("pipeline_runs")
        row = self._execute(
            f"INSERT INTO {runs_table} (pipeline_name, status, variables, scheduler_name, created_at, updated_at) "
            f"VALUES (%s, %s, %s, %s, %s, %s) RETURNING *",
            (
                pipeline_name,
                RunStatus.PENDING.value,
                self._serialize(variables or {}),
                scheduler_name,
                now,
                now,
            ),
        )
        assert row is not None
        return self._row_to_run(row)

    def get_pipeline_run(self, run_id: int) -> RunRecord | None:
        runs_table = self._table_name("pipeline_runs")
        row = self._query_one(f"SELECT * FROM {runs_table} WHERE id = %s", (run_id,))
        return self._row_to_run(row) if row else None

    def list_pipeline_runs(self, pipeline_name: str, limit: int = 50) -> list[RunRecord]:
        runs_table = self._table_name("pipeline_runs")
        rows = self._query_all(
            f"SELECT * FROM {runs_table} WHERE pipeline_name = %s ORDER BY id DESC LIMIT %s",
            (pipeline_name, limit),
        )
        return [self._row_to_run(row) for row in rows]

    def list_scheduler_runs(self, scheduler_name: str, limit: int = 50) -> list[RunRecord]:
        runs_table = self._table_name("pipeline_runs")
        rows = self._query_all(
            f"SELECT * FROM {runs_table} WHERE scheduler_name = %s ORDER BY id DESC LIMIT %s",
            (scheduler_name, limit),
        )
        return [self._row_to_run(row) for row in rows]

    def cancel_pipeline_run(self, run_id: int) -> RunRecord | None:
        """Best-effort cancel: atomically mark a NON-terminal run as cancelled.
        The background worker is not interrupted, but the status reflects the
        cancellation, and a worker finishing afterwards won't overwrite it (it
        finalises only a still-``running`` run). Returns None if the run does
        not exist; the unchanged run if it was already terminal."""
        now = self._now()
        runs_table = self._table_name("pipeline_runs")
        row = self._execute(
            f"UPDATE {runs_table} SET status = %s, finished_at = %s, updated_at = %s "
            f"WHERE id = %s AND status NOT IN (%s, %s, %s) RETURNING *",
            (
                RunStatus.CANCELLED.value, now, now, run_id,
                RunStatus.SUCCESS.value, RunStatus.FAILED.value, RunStatus.CANCELLED.value,
            ),
        )
        if row is not None:
            return self._row_to_run(row)
        # not cancelled: either the run doesn't exist, or it was already terminal
        return self.get_pipeline_run(run_id)

    def update_pipeline_run(
        self,
        run_id: int,
        *,
        status: str | None = None,
        result: dict[str, Any] | None = None,
        error: str | None = None,
        started_at: str | None = None,
        finished_at: str | None = None,
        where_status: str | None = None,
    ) -> RunRecord | None:
        """Update a run. When ``where_status`` is given, the update only applies
        if the run is currently in that status (a guarded transition, e.g. only
        finalise a run that is still ``running`` — never overwrite a cancel);
        returns None when the guard doesn't match. Without a guard, a missing
        run raises ValueError."""
        set_clauses = ["updated_at = %s"]
        params: list[Any] = [self._now()]
        if status is not None:
            set_clauses.append("status = %s")
            params.append(status)
        if result is not None:
            set_clauses.append("result = %s")
            params.append(self._serialize(result))
        if error is not None:
            set_clauses.append("error = %s")
            params.append(error)
        if started_at is not None:
            set_clauses.append("started_at = %s")
            params.append(started_at)
        if finished_at is not None:
            set_clauses.append("finished_at = %s")
            params.append(finished_at)

        where = "id = %s"
        params.append(run_id)
        if where_status is not None:
            where += " AND status = %s"
            params.append(where_status)

        runs_table = self._table_name("pipeline_runs")
        row = self._execute(
            f"UPDATE {runs_table} SET {', '.join(set_clauses)} WHERE {where} RETURNING *",
            tuple(params),
        )
        if row is None:
            if where_status is not None:
                return None  # guard didn't match (already terminal/cancelled)
            raise ValueError(f"Pipeline run {run_id!r} does not exist")
        return self._row_to_run(row)

    def _query_one(self, query: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        with self.connection.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchone()

    def _query_all(self, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self.connection.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchall()

    def _execute(self, query: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        with self.connection.cursor() as cur:
            cur.execute(query, params)
            result = cur.fetchone() if cur.description else None
        self.connection.commit()
        return result

    def create_bloc(
        self,
        name: str,
        bloc_type: str,
        dependencies: list[str] | None = None,
        config: dict[str, Any] | None = None,
        description: str | None = None,
    ) -> BlocRecord:
        now = self._now()
        blocs_table = self._table_name("blocs")
        row = self._execute(
            f"INSERT INTO {blocs_table} (name, bloc_type, dependencies, config, description, created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING *",
            (
                name,
                bloc_type,
                self._serialize(dependencies or []),
                self._serialize(config or {}),
                description,
                now,
                now,
            ),
        )
        assert row is not None
        return self._row_to_bloc(row)

    def get_bloc(self, name: str) -> BlocRecord | None:
        blocs_table = self._table_name("blocs")
        row = self._query_one(f"SELECT * FROM {blocs_table} WHERE name = %s", (name,))
        return self._row_to_bloc(row) if row else None

    def list_blocs(self) -> list[BlocRecord]:
        blocs_table = self._table_name("blocs")
        rows = self._query_all(f"SELECT * FROM {blocs_table} ORDER BY name")
        return [self._row_to_bloc(row) for row in rows]

    def update_bloc(
        self,
        name: str,
        bloc_type: str | None = None,
        dependencies: list[str] | None = None,
        config: dict[str, Any] | None = None,
        description: str | None = None,
    ) -> BlocRecord:
        existing = self.get_bloc(name)
        if existing is None:
            raise ValueError(f"Bloc {name!r} does not exist")

        updated_type = bloc_type or existing.bloc_type
        updated_dependencies = dependencies if dependencies is not None else existing.dependencies
        updated_config = config if config is not None else existing.config
        updated_description = description if description is not None else existing.description
        now = self._now()

        blocs_table = self._table_name("blocs")
        row = self._execute(
            f"UPDATE {blocs_table} SET bloc_type = %s, dependencies = %s, config = %s, description = %s, updated_at = %s WHERE name = %s RETURNING *",
            (
                updated_type,
                self._serialize(updated_dependencies),
                self._serialize(updated_config),
                updated_description,
                now,
                name,
            ),
        )
        assert row is not None
        return self._row_to_bloc(row)

    def delete_bloc(self, name: str) -> bool:
        blocs_table = self._table_name("blocs")
        with self.connection.cursor() as cur:
            cur.execute(f"DELETE FROM {blocs_table} WHERE name = %s", (name,))
            deleted = cur.rowcount
        self.connection.commit()
        return deleted > 0

    def create_pipeline(
        self,
        name: str,
        stages: list[list[str]],
        description: str | None = None,
    ) -> PipelineRecord:
        self._ensure_blocs_exist(stages)
        now = self._now()
        pipelines_table = self._table_name("pipelines")
        row = self._execute(
            f"INSERT INTO {pipelines_table} (name, stages, description, created_at, updated_at) VALUES (%s, %s, %s, %s, %s) RETURNING *",
            (
                name,
                self._serialize(stages),
                description,
                now,
                now,
            ),
        )
        assert row is not None
        return self._row_to_pipeline(row)

    def get_pipeline(self, name: str) -> PipelineRecord | None:
        pipelines_table = self._table_name("pipelines")
        row = self._query_one(f"SELECT * FROM {pipelines_table} WHERE name = %s", (name,))
        return self._row_to_pipeline(row) if row else None

    def list_pipelines(self) -> list[PipelineRecord]:
        pipelines_table = self._table_name("pipelines")
        rows = self._query_all(f"SELECT * FROM {pipelines_table} ORDER BY name")
        return [self._row_to_pipeline(row) for row in rows]

    def update_pipeline(
        self,
        name: str,
        stages: list[list[str]] | None = None,
        description: str | None = None,
    ) -> PipelineRecord:
        existing = self.get_pipeline(name)
        if existing is None:
            raise ValueError(f"Pipeline {name!r} does not exist")

        updated_stages = stages if stages is not None else existing.stages
        self._ensure_blocs_exist(updated_stages)
        updated_description = description if description is not None else existing.description
        now = self._now()

        pipelines_table = self._table_name("pipelines")
        row = self._execute(
            f"UPDATE {pipelines_table} SET stages = %s, description = %s, updated_at = %s WHERE name = %s RETURNING *",
            (
                self._serialize(updated_stages),
                updated_description,
                now,
                name,
            ),
        )
        assert row is not None
        return self._row_to_pipeline(row)

    def delete_pipeline(self, name: str) -> bool:
        pipelines_table = self._table_name("pipelines")
        with self.connection.cursor() as cur:
            cur.execute(f"DELETE FROM {pipelines_table} WHERE name = %s", (name,))
            deleted = cur.rowcount
        self.connection.commit()
        return deleted > 0

    def _validate_cron_expression(self, expression: str) -> None:
        from th2etl.scheduler.helpers import CronTrigger

        CronTrigger(expression)

    def create_trigger(
        self,
        name: str,
        pipeline_name: str,
        cron_expression: str,
        description: str | None = None,
    ) -> TriggerRecord:
        self._validate_cron_expression(cron_expression)
        pipeline_id = self._require_pipeline_id(pipeline_name)
        now = self._now()
        triggers_table = self._table_name("triggers")
        row = self._execute(
            f"INSERT INTO {triggers_table} (name, pipeline_id, cron_expression, description, created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s) RETURNING *",
            (name, pipeline_id, cron_expression, description, now, now),
        )
        assert row is not None
        trigger = self._row_to_trigger(row)
        self._notify_trigger_change(trigger)
        return trigger

    def get_trigger(self, name: str) -> TriggerRecord | None:
        triggers_table = self._table_name("triggers")
        row = self._query_one(f"SELECT * FROM {triggers_table} WHERE name = %s", (name,))
        return self._row_to_trigger(row) if row else None

    def list_triggers(self) -> list[TriggerRecord]:
        triggers_table = self._table_name("triggers")
        rows = self._query_all(f"SELECT * FROM {triggers_table} ORDER BY name")
        return [self._row_to_trigger(row) for row in rows]

    def update_trigger(
        self,
        name: str,
        pipeline_name: str | None = None,
        cron_expression: str | None = None,
        description: str | None = None,
    ) -> TriggerRecord:
        existing = self.get_trigger(name)
        if existing is None:
            raise ValueError(f"Trigger {name!r} does not exist")

        pipeline_id = self._require_pipeline_id(pipeline_name) if pipeline_name else existing.pipeline_id
        updated_cron = cron_expression if cron_expression is not None else existing.cron_expression
        self._validate_cron_expression(updated_cron)
        updated_description = description if description is not None else existing.description
        now = self._now()

        triggers_table = self._table_name("triggers")
        row = self._execute(
            f"UPDATE {triggers_table} SET pipeline_id = %s, cron_expression = %s, description = %s, updated_at = %s WHERE name = %s RETURNING *",
            (pipeline_id, updated_cron, updated_description, now, name),
        )
        assert row is not None
        trigger = self._row_to_trigger(row)
        self._notify_trigger_change(trigger)
        return trigger

    def delete_trigger(self, name: str) -> bool:
        triggers_table = self._table_name("triggers")
        with self.connection.cursor() as cur:
            cur.execute(f"DELETE FROM {triggers_table} WHERE name = %s", (name,))
            deleted = cur.rowcount
        self.connection.commit()
        return deleted > 0

    def create_scheduler(
        self,
        name: str,
        pipeline_name: str,
        trigger_name: str,
        description: str | None = None,
        variables: dict[str, Any] | None = None,
        active: bool = True,
    ) -> SchedulerRecord:
        pipeline_id = self._require_pipeline_id(pipeline_name)
        trigger_id = self._require_trigger_id(trigger_name)
        now = self._now()
        schedulers_table = self._table_name("schedulers")
        row = self._execute(
            f"INSERT INTO {schedulers_table} (name, pipeline_id, trigger_id, description, variables, active, created_at, updated_at) "
            f"VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING *",
            (name, pipeline_id, trigger_id, description, self._serialize(variables or {}), active, now, now),
        )
        assert row is not None
        scheduler = self._row_to_scheduler(row)
        return scheduler

    def get_scheduler(self, name: str) -> SchedulerRecord | None:
        schedulers_table = self._table_name("schedulers")
        row = self._query_one(f"SELECT * FROM {schedulers_table} WHERE name = %s", (name,))
        return self._row_to_scheduler(row) if row else None

    def list_schedulers(self) -> list[SchedulerRecord]:
        schedulers_table = self._table_name("schedulers")
        rows = self._query_all(f"SELECT * FROM {schedulers_table} ORDER BY name")
        return [self._row_to_scheduler(row) for row in rows]

    def update_scheduler(
        self,
        name: str,
        pipeline_name: str | None = None,
        trigger_name: str | None = None,
        description: str | None = None,
        variables: dict[str, Any] | None = None,
        active: bool | None = None,
    ) -> SchedulerRecord:
        existing = self.get_scheduler(name)
        if existing is None:
            raise ValueError(f"Scheduler {name!r} does not exist")

        pipeline_id = self._require_pipeline_id(pipeline_name or existing.pipeline_name)
        trigger_id = self._require_trigger_id(trigger_name or existing.trigger_name)
        updated_description = description if description is not None else existing.description
        updated_variables = variables if variables is not None else existing.variables
        updated_active = active if active is not None else existing.active
        now = self._now()

        schedulers_table = self._table_name("schedulers")
        row = self._execute(
            f"UPDATE {schedulers_table} SET pipeline_id = %s, trigger_id = %s, description = %s, "
            f"variables = %s, active = %s, updated_at = %s WHERE name = %s RETURNING *",
            (pipeline_id, trigger_id, updated_description, self._serialize(updated_variables), updated_active, now, name),
        )
        assert row is not None
        scheduler = self._row_to_scheduler(row)
        return scheduler

    def update_scheduler_variables(self, name: str, variables: dict[str, Any]) -> SchedulerRecord:
        """Replace a scheduler's runtime variables (used for e.g. token rotation)."""
        now = self._now()
        schedulers_table = self._table_name("schedulers")
        row = self._execute(
            f"UPDATE {schedulers_table} SET variables = %s, updated_at = %s WHERE name = %s RETURNING *",
            (self._serialize(variables), now, name),
        )
        if row is None:
            raise ValueError(f"Scheduler {name!r} does not exist")
        return self._row_to_scheduler(row)

    def delete_scheduler(self, name: str) -> bool:
        schedulers_table = self._table_name("schedulers")
        with self.connection.cursor() as cur:
            cur.execute(f"DELETE FROM {schedulers_table} WHERE name = %s", (name,))
            deleted = cur.rowcount
        self.connection.commit()
        return deleted > 0

    def _ensure_blocs_exist(self, stages: list[list[str]]) -> None:
        for stage in stages:
            for bloc_name in stage:
                if self.get_bloc(bloc_name) is None:
                    raise ValueError(f"Bloc {bloc_name!r} does not exist")

    def _require_pipeline_id(self, pipeline_name: str) -> int:
        pipelines_table = self._table_name("pipelines")
        row = self._query_one(f"SELECT id FROM {pipelines_table} WHERE name = %s", (pipeline_name,))
        if not row:
            raise ValueError(f"Pipeline {pipeline_name!r} does not exist")
        return row["id"]

    def _require_trigger_id(self, trigger_name: str) -> int:
        triggers_table = self._table_name("triggers")
        row = self._query_one(f"SELECT id FROM {triggers_table} WHERE name = %s", (trigger_name,))
        if not row:
            raise ValueError(f"Trigger {trigger_name!r} does not exist")
        return row["id"]
