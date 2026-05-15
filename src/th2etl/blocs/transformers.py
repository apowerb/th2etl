from __future__ import annotations

import logging
from typing import Any, Sequence
import uuid

import requests

from th2etl.blocs.base import TransformerBloc
from th2etl.helpers.security import create_access_token
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
        logger.info(f"Running ADK agent '{self.config.agent_id}' for user '{self.config.user_id}'")
        
        jwt_token = create_access_token(data = {"user_id": self.config.user_id, "type": "access"})
        headers = {
            "Authorization": f"Bearer {jwt_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        payload = {
            "agent_id": self.config.agent_id,
            "user_id": self.config.user_id,
            "session_id": str(uuid.uuid4()),
            "new_message": {
                "role": "user",
                "parts": [{"text": self.config.message_text}],
            },
        }

        try:
            response = requests.post(self.config.url, headers=headers, json=payload)
            response.raise_for_status()
            result = response.json()
            run_context.context_vars[f"{self.name}_result"] = result
            logger.info(f"Successfully ran agent '{self.config.agent_id}' with session '{payload['session_id']}'")
            logger.debug("Agent response: %s", result)
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to run ADK agent: {e}")
            if e.response is not None:
                logger.error(f"Response status: {e.response.status_code}")
                logger.error(f"Response body: {e.response.text}")
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
        jwt_token = create_access_token(data={"user_id": self.config.user_id, "type": "system"})
        headers = {"Authorization": f"Bearer {jwt_token}"}

        try:
            response = requests.post(self.config.url, headers=headers)
            response.raise_for_status()
            result = response.json()
            run_context.context_vars[f"{self.name}_result"] = result
            logger.info("Successfully refreshed webhooks.")
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to refresh webhooks: {e}")
            raise
