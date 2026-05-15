from __future__ import annotations

import logging
from typing import Any, Sequence

import requests

from th2etl.blocs.base import TransformerBloc
from th2etl.pipelines.context import RunContext
from th2etl.blocs.schemas import RunAdkAgentsConfig, RefreshWebhooksConfig

logger = logging.getLogger(__name__)


class RunAdkAgentsBloc(TransformerBloc):
    """A transformer that runs an ADK agent via an API call."""

    def __init__(
        self,
        name: str,
        dependencies: Sequence[str] | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(name=name, dependencies=dependencies)
        self.config = RunAdkAgentsConfig(**(config or {}))

    def execute(self, run_context: RunContext) -> None:
        logger.info(f"Running ADK agent '{self.config.agent_id}'")
        headers = {"Authorization": f"Bearer {self.config.jwt_token}"}
        payload = {"message": self.config.message}
        
        try:
            response = requests.post(self.config.url, headers=headers, json=payload)
            response.raise_for_status()
            result = response.json()
            run_context.context_vars[f"{self.name}_result"] = result
            logger.info(f"Successfully ran agent '{self.config.agent_id}'")
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to run ADK agent: {e}")
            raise


class RefreshWebhooksBloc(TransformerBloc):
    """A transformer that refreshes webhooks via an API call."""

    def __init__(
        self,
        name: str,
        dependencies: Sequence[str] | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(name=name, dependencies=dependencies)
        self.config = RefreshWebhooksConfig(**(config or {}))

    def execute(self, run_context: RunContext) -> None:
        logger.info(f"Refreshing webhooks at '{self.config.url}'")
        headers = {"Authorization": f"Bearer {self.config.jwt_token}"}
        
        try:
            response = requests.post(self.config.url, headers=headers)
            response.raise_for_status()
            result = response.json()
            run_context.context_vars[f"{self.name}_result"] = result
            logger.info("Successfully refreshed webhooks.")
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to refresh webhooks: {e}")
            raise
