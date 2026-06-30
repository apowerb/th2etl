from __future__ import annotations

import logging
from typing import Any
import uuid

import requests

from th2etl.blocs.base import TransformerBloc
from th2etl.pipelines.context import RunContext
from th2etl.blocs.schemas import RunAdkAgentsConfig, RunAdkFromJwtConfig, RefreshWebhooksConfig
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
        # Resolve per-run values from the run variables (context_vars), falling
        # back to the static bloc config. th2agent supplies agent_id/user_id/
        # message_text per run, so these normally arrive as run variables.
        cv = run_context.context_vars
        agent_id = cv.get("agent_id") or self.config.agent_id
        user_id = cv.get("user_id") or self.config.user_id
        message_text = cv.get("message_text") or self.config.message_text
        data = cv["data"] if "data" in cv else self.config.data

        missing = [n for n, v in (("agent_id", agent_id), ("user_id", user_id), ("message_text", message_text)) if not v]
        if missing:
            raise ValueError(
                f"RunAdkAgentsBloc '{self.name}': missing {missing} — supply via run variables or bloc config"
            )

        logger.info(f"Running ADK agent '{agent_id}' for user '{user_id}'")

        # Generate JWT token on the fly
        jwt_token = create_access_token(data={"sub": user_id})

        headers = {
            "Authorization": f"Bearer {jwt_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        # Construct the full URL from the base_url
        url = f"{self.config.base_url.rstrip('/')}/api/adk/run"

        payload = {
            "agent_name": agent_id,
            "user_id": user_id,
            "session_id": str(uuid.uuid4()),
            "data": data,
            "run_mode": self.config.run_mode,
            "streaming": self.config.streaming,
            "new_message": {
                "role": "user",
                "parts": [{"text": message_text}],
            },
        }

        try:
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            result = response.json()
            run_context.context_vars[f"{self.name}_result"] = result
            logger.info(f"Successfully ran agent '{agent_id}' with session '{payload['session_id']}'")
            logger.debug("Agent response: %s", result)
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to run ADK agent: {e}")
            if e.response is not None:
                logger.error(f"Response status: {e.response.status_code}")
                logger.error(f"Response body: {e.response.text}")
            raise


class RunAdkFromJwtBloc(TransformerBloc):
    """Runs an ADK agent from a refresh JWT, faithful to the MageAI flow:
    forwards the ``jwt_token`` run variable to ``/api/adk/run_from_jwt`` as a
    Bearer header. th2agent rotates the token after a successful run."""

    def __init__(self, name: str, config: dict[str, Any] | None = None) -> None:
        super().__init__(name=name)
        self.config = RunAdkFromJwtConfig(**(config or {}))

    def execute(self, run_context: RunContext) -> None:
        cv = run_context.context_vars
        jwt_token = cv.get("jwt_token") or self.config.jwt_token
        agent_id = cv.get("agent_id") or self.config.agent_id
        # presence test (not truthiness) so an explicit empty {} is honoured
        data = cv.get("agent_meta", cv.get("data", self.config.data))

        if not jwt_token:
            raise ValueError(
                f"RunAdkFromJwtBloc '{self.name}': missing jwt_token — supply via run variables or bloc config"
            )

        logger.info(f"Running ADK agent from JWT (agent_id={agent_id})")
        url = f"{self.config.base_url.rstrip('/')}/api/adk/run_from_jwt"
        headers = {
            "Authorization": f"Bearer {jwt_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        payload = {"agent_id": agent_id, "data": data}

        try:
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            result = response.json()
            run_context.context_vars[f"{self.name}_result"] = result
            logger.info(f"Successfully ran agent from JWT (agent_id={agent_id})")
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to run ADK agent from JWT: {e}")
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
