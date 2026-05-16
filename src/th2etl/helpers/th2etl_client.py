from __future__ import annotations

from typing import Any

from .client import HttpClient


class Th2etlClient(HttpClient):
    """An API client for interacting with the th2etl service."""

    def __init__(self, base_url: str = "http://127.0.0.1:8000", **kwargs: Any):
        super().__init__(base_url=base_url, **kwargs)

    # --- Blocs ---
    def create_bloc(self, name: str, bloc_type: str, config: dict, dependencies: list[str] | None = None, description: str | None = None) -> dict:
        return self.post("/blocs", json_data={
            "name": name,
            "bloc_type": bloc_type,
            "config": config,
            "dependencies": dependencies,
            "description": description,
        })

    def list_blocs(self) -> list[dict]:
        return self.get("/blocs")

    def get_bloc(self, name: str) -> dict:
        return self.get(f"/blocs/{name}")

    def update_bloc(self, name: str, **kwargs: Any) -> dict:
        return self.put(f"/blocs/{name}", json_data=kwargs)

    def delete_bloc(self, name: str) -> None:
        self.delete(f"/blocs/{name}")

    # --- Pipelines ---
    def create_pipeline(self, name: str, bloc_names: list[str], description: str | None = None) -> dict:
        return self.post("/pipelines", json_data={
            "name": name,
            "bloc_names": bloc_names,
            "description": description,
        })

    def list_pipelines(self) -> list[dict]:
        return self.get("/pipelines")

    def get_pipeline(self, name: str) -> dict:
        return self.get(f"/pipelines/{name}")

    def update_pipeline(self, name: str, **kwargs: Any) -> dict:
        return self.put(f"/pipelines/{name}", json_data=kwargs)

    def delete_pipeline(self, name: str) -> None:
        self.delete(f"/pipelines/{name}")

    # --- Triggers ---
    def create_trigger(self, name: str, pipeline_name: str, cron_expression: str, description: str | None = None) -> dict:
        return self.post("/triggers", json_data={
            "name": name,
            "pipeline_name": pipeline_name,
            "cron_expression": cron_expression,
            "description": description,
        })

    def list_triggers(self) -> list[dict]:
        return self.get("/triggers")

    def get_trigger(self, name: str) -> dict:
        return self.get(f"/triggers/{name}")

    def update_trigger(self, name: str, **kwargs: Any) -> dict:
        return self.put(f"/triggers/{name}", json_data=kwargs)

    def delete_trigger(self, name: str) -> None:
        self.delete(f"/triggers/{name}")

    # --- Schedulers ---
    def create_scheduler(self, name: str, pipeline_name: str, trigger_name: str, description: str | None = None) -> dict:
        return self.post("/schedulers", json_data={
            "name": name,
            "pipeline_name": pipeline_name,
            "trigger_name": trigger_name,
            "description": description,
        })

    def list_schedulers(self) -> list[dict]:
        return self.get("/schedulers")

    def get_scheduler(self, name: str) -> dict:
        return self.get(f"/schedulers/{name}")

    def update_scheduler(self, name: str, **kwargs: Any) -> dict:
        return self.put(f"/schedulers/{name}", json_data=kwargs)

    def delete_scheduler(self, name: str) -> None:
        self.delete(f"/schedulers/{name}")

    # --- Health Check ---
    def health_check(self) -> dict:
        return self.get("/health")
