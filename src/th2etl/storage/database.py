from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import psycopg
from psycopg.rows import dict_row

from ..configs.settings import Settings


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
    bloc_names: list[str]
    description: str | None
    created_at: str
    updated_at: str


@dataclass
class TriggerRecord:
    id: int | None
    name: str
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
    created_at: str
    updated_at: str


class DatabaseStorage:
    def __init__(self, dsn: str | None = None, settings: Settings | None = None) -> None:
        if settings is not None:
            dsn = settings.database_dsn
        if not dsn:
            raise ValueError(
                "DatabaseStorage requires either a DSN or a Settings instance with database connection settings"
            )

        self.dsn = dsn
        self.connection = psycopg.connect(self.dsn, row_factory=dict_row)
        self._create_tables()

    @classmethod
    def from_settings(cls, settings: Settings) -> "DatabaseStorage":
        return cls(settings=settings)

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "DatabaseStorage":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def _create_tables(self) -> None:
        with self.connection.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS blocs (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    bloc_type TEXT NOT NULL,
                    dependencies JSONB NOT NULL,
                    config JSONB NOT NULL,
                    description TEXT,
                    created_at TIMESTAMPTZ NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL
                );

                CREATE TABLE IF NOT EXISTS pipelines (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    bloc_names JSONB NOT NULL,
                    description TEXT,
                    created_at TIMESTAMPTZ NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL
                );

                CREATE TABLE IF NOT EXISTS triggers (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    cron_expression TEXT NOT NULL,
                    description TEXT,
                    created_at TIMESTAMPTZ NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL
                );

                CREATE TABLE IF NOT EXISTS schedulers (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    pipeline_id INTEGER NOT NULL REFERENCES pipelines(id) ON DELETE CASCADE,
                    trigger_id INTEGER NOT NULL REFERENCES triggers(id) ON DELETE CASCADE,
                    description TEXT,
                    created_at TIMESTAMPTZ NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL
                );
                """
            )
        self.connection.commit()

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
            bloc_names=row["bloc_names"],
            description=row["description"],
            created_at=row["created_at"].isoformat() if row["created_at"] else "",
            updated_at=row["updated_at"].isoformat() if row["updated_at"] else "",
        )

    def _row_to_trigger(self, row: dict[str, Any]) -> TriggerRecord:
        return TriggerRecord(
            id=row["id"],
            name=row["name"],
            cron_expression=row["cron_expression"],
            description=row["description"],
            created_at=row["created_at"].isoformat() if row["created_at"] else "",
            updated_at=row["updated_at"].isoformat() if row["updated_at"] else "",
        )

    def _row_to_scheduler(self, row: dict[str, Any]) -> SchedulerRecord:
        pipeline_row = self._query_one("SELECT name FROM pipelines WHERE id = %s", (row["pipeline_id"],))
        trigger_row = self._query_one("SELECT name FROM triggers WHERE id = %s", (row["trigger_id"],))
        return SchedulerRecord(
            id=row["id"],
            name=row["name"],
            pipeline_name=pipeline_row["name"],
            trigger_name=trigger_row["name"],
            description=row["description"],
            created_at=row["created_at"].isoformat() if row["created_at"] else "",
            updated_at=row["updated_at"].isoformat() if row["updated_at"] else "",
        )

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
        row = self._execute(
            "INSERT INTO blocs (name, bloc_type, dependencies, config, description, created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING *",
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
        row = self._query_one("SELECT * FROM blocs WHERE name = %s", (name,))
        return self._row_to_bloc(row) if row else None

    def list_blocs(self) -> list[BlocRecord]:
        rows = self._query_all("SELECT * FROM blocs ORDER BY name")
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

        row = self._execute(
            "UPDATE blocs SET bloc_type = %s, dependencies = %s, config = %s, description = %s, updated_at = %s WHERE name = %s RETURNING *",
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
        with self.connection.cursor() as cur:
            cur.execute("DELETE FROM blocs WHERE name = %s", (name,))
            deleted = cur.rowcount
        self.connection.commit()
        return deleted > 0

    def create_pipeline(
        self,
        name: str,
        bloc_names: list[str],
        description: str | None = None,
    ) -> PipelineRecord:
        self._ensure_blocs_exist(bloc_names)
        now = self._now()
        row = self._execute(
            "INSERT INTO pipelines (name, bloc_names, description, created_at, updated_at) VALUES (%s, %s, %s, %s, %s) RETURNING *",
            (
                name,
                self._serialize(bloc_names),
                description,
                now,
                now,
            ),
        )
        assert row is not None
        return self._row_to_pipeline(row)

    def get_pipeline(self, name: str) -> PipelineRecord | None:
        row = self._query_one("SELECT * FROM pipelines WHERE name = %s", (name,))
        return self._row_to_pipeline(row) if row else None

    def list_pipelines(self) -> list[PipelineRecord]:
        rows = self._query_all("SELECT * FROM pipelines ORDER BY name")
        return [self._row_to_pipeline(row) for row in rows]

    def update_pipeline(
        self,
        name: str,
        bloc_names: list[str] | None = None,
        description: str | None = None,
    ) -> PipelineRecord:
        existing = self.get_pipeline(name)
        if existing is None:
            raise ValueError(f"Pipeline {name!r} does not exist")

        updated_bloc_names = bloc_names if bloc_names is not None else existing.bloc_names
        self._ensure_blocs_exist(updated_bloc_names)
        updated_description = description if description is not None else existing.description
        now = self._now()

        row = self._execute(
            "UPDATE pipelines SET bloc_names = %s, description = %s, updated_at = %s WHERE name = %s RETURNING *",
            (
                self._serialize(updated_bloc_names),
                updated_description,
                now,
                name,
            ),
        )
        assert row is not None
        return self._row_to_pipeline(row)

    def delete_pipeline(self, name: str) -> bool:
        with self.connection.cursor() as cur:
            cur.execute("DELETE FROM pipelines WHERE name = %s", (name,))
            deleted = cur.rowcount
        self.connection.commit()
        return deleted > 0

    def create_trigger(
        self,
        name: str,
        cron_expression: str,
        description: str | None = None,
    ) -> TriggerRecord:
        now = self._now()
        row = self._execute(
            "INSERT INTO triggers (name, cron_expression, description, created_at, updated_at) VALUES (%s, %s, %s, %s, %s) RETURNING *",
            (name, cron_expression, description, now, now),
        )
        assert row is not None
        return self._row_to_trigger(row)

    def get_trigger(self, name: str) -> TriggerRecord | None:
        row = self._query_one("SELECT * FROM triggers WHERE name = %s", (name,))
        return self._row_to_trigger(row) if row else None

    def list_triggers(self) -> list[TriggerRecord]:
        rows = self._query_all("SELECT * FROM triggers ORDER BY name")
        return [self._row_to_trigger(row) for row in rows]

    def update_trigger(
        self,
        name: str,
        cron_expression: str | None = None,
        description: str | None = None,
    ) -> TriggerRecord:
        existing = self.get_trigger(name)
        if existing is None:
            raise ValueError(f"Trigger {name!r} does not exist")

        updated_cron = cron_expression if cron_expression is not None else existing.cron_expression
        updated_description = description if description is not None else existing.description
        now = self._now()

        row = self._execute(
            "UPDATE triggers SET cron_expression = %s, description = %s, updated_at = %s WHERE name = %s RETURNING *",
            (updated_cron, updated_description, now, name),
        )
        assert row is not None
        return self._row_to_trigger(row)

    def delete_trigger(self, name: str) -> bool:
        with self.connection.cursor() as cur:
            cur.execute("DELETE FROM triggers WHERE name = %s", (name,))
            deleted = cur.rowcount
        self.connection.commit()
        return deleted > 0

    def create_scheduler(
        self,
        name: str,
        pipeline_name: str,
        trigger_name: str,
        description: str | None = None,
    ) -> SchedulerRecord:
        pipeline_id = self._require_pipeline_id(pipeline_name)
        trigger_id = self._require_trigger_id(trigger_name)
        now = self._now()
        row = self._execute(
            "INSERT INTO schedulers (name, pipeline_id, trigger_id, description, created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s) RETURNING *",
            (name, pipeline_id, trigger_id, description, now, now),
        )
        assert row is not None
        return self._row_to_scheduler(row)

    def get_scheduler(self, name: str) -> SchedulerRecord | None:
        row = self._query_one("SELECT * FROM schedulers WHERE name = %s", (name,))
        return self._row_to_scheduler(row) if row else None

    def list_schedulers(self) -> list[SchedulerRecord]:
        rows = self._query_all("SELECT * FROM schedulers ORDER BY name")
        return [self._row_to_scheduler(row) for row in rows]

    def update_scheduler(
        self,
        name: str,
        pipeline_name: str | None = None,
        trigger_name: str | None = None,
        description: str | None = None,
    ) -> SchedulerRecord:
        existing = self.get_scheduler(name)
        if existing is None:
            raise ValueError(f"Scheduler {name!r} does not exist")

        pipeline_id = self._require_pipeline_id(pipeline_name or existing.pipeline_name)
        trigger_id = self._require_trigger_id(trigger_name or existing.trigger_name)
        updated_description = description if description is not None else existing.description
        now = self._now()

        row = self._execute(
            "UPDATE schedulers SET pipeline_id = %s, trigger_id = %s, description = %s, updated_at = %s WHERE name = %s RETURNING *",
            (pipeline_id, trigger_id, updated_description, now, name),
        )
        assert row is not None
        return self._row_to_scheduler(row)

    def delete_scheduler(self, name: str) -> bool:
        with self.connection.cursor() as cur:
            cur.execute("DELETE FROM schedulers WHERE name = %s", (name,))
            deleted = cur.rowcount
        self.connection.commit()
        return deleted > 0

    def _ensure_blocs_exist(self, bloc_names: list[str]) -> None:
        for bloc_name in bloc_names:
            if self.get_bloc(bloc_name) is None:
                raise ValueError(f"Bloc {bloc_name!r} does not exist")

    def _require_pipeline_id(self, pipeline_name: str) -> int:
        row = self._query_one("SELECT id FROM pipelines WHERE name = %s", (pipeline_name,))
        if not row:
            raise ValueError(f"Pipeline {pipeline_name!r} does not exist")
        return row["id"]

    def _require_trigger_id(self, trigger_name: str) -> int:
        row = self._query_one("SELECT id FROM triggers WHERE name = %s", (trigger_name,))
        if not row:
            raise ValueError(f"Trigger {trigger_name!r} does not exist")
        return row["id"]
