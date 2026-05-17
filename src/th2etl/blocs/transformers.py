from __future__ import annotations

import logging
from typing import Any, Sequence
import uuid

import requests

from th2etl.blocs.base import TransformerBloc
from th2etl.pipelines.context import RunContext
from th2etl.blocs.schemas import RunAdkAgentsConfig, RefreshWebhooksConfig
from th2etl.helpers.security import create_access_token

logger = logging.getLogger(__name__)


class RunAdkAgentsBloc(TransformerBloc):
    """A transformer that runs an ADK agent via an API call."""

    def __init__(
        self,
        name: str,
        config: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(name=name)
        self.config = RunAdkAgentsConfig(**(config or {}))

    def execute(self, run_context: RunContext) -> None:
        logger.info(f"Running ADK agent '{self.config.agent_id}' for user '{self.config.user_id}'")
        
        # Generate JWT token on the fly
        jwt_token = create_access_token(data={"sub": self.config.user_id})
        
        headers = {
            "Authorization": f"Bearer {jwt_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        # Construct the full URL from the base_url
        url = f"{self.config.base_url.rstrip('/')}/api/adk/run"

        payload = {
            "agent_name": self.config.agent_id,
            "user_id": self.config.user_id,
            "session_id": str(uuid.uuid4()),
            "data": self.config.data,
            "run_mode": self.config.run_mode,
            "streaming": self.config.streaming,
            "new_message": {
                "role": "user",
                "parts": [{"text": self.config.message_text}],
            },
        }

        try:
            response = requests.post(url, headers=headers, json=payload)
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
        config: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(name=name)
        self.config = RefreshWebhooksConfig(**(config or {}))

    def execute(self, run_context: RunContext) -> None:
        logger.info(f"Refreshing webhooks at '{self.config.url}' for user '{self.config.user_id}'")
        
        # Generate JWT token on the fly
        jwt_token = create_access_token(data={"sub": self.config.user_id})
        
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
