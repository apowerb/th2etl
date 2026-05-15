from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class BaseBlocConfig(BaseModel):
    """Base schema for bloc configurations."""

    class Config:
        extra = "allow"


class CsvLoaderConfig(BaseBlocConfig):
    """Configuration for loading data from a CSV file."""

    file_path: str = Field(..., description="The path to the CSV file to load.")
    delimiter: str = Field(",", description="The delimiter used in the CSV file.")


class PostgresLoaderConfig(BaseBlocConfig):
    """Configuration for loading data from a PostgreSQL database."""

    query: str = Field(..., description="The SQL query to execute to load the data.")


class ApiLoaderConfig(BaseBlocConfig):
    """Configuration for loading data from a web API."""

    url: str = Field(..., description="The URL of the API endpoint to fetch data from.")
    method: str = Field("GET", description="The HTTP method to use for the request (e.g., GET, POST).")
    params: dict[str, Any] | None = Field(None, description="Optional URL parameters for the request.")
    headers: dict[str, Any] | None = Field(None, description="Optional HTTP headers for the request.")
    json_payload: dict[str, Any] | None = Field(None, alias="json", description="Optional JSON body for the request.")


class ExampleTransformerConfig(BaseBlocConfig):
    """Configuration for the example transformer."""

    factor: float = Field(1.0, description="The factor to multiply values by.")


class ExampleExporterConfig(BaseBlocConfig):
    """Configuration for the example exporter."""

    destination: str = Field("stdout", description="The destination for the exported data.")


class ScriptBlocConfig(BaseBlocConfig):
    """Configuration for a bloc that executes a Python script."""

    script_path: str = Field(..., description="The path to the Python script to execute.")


class RunAdkAgentsConfig(BaseBlocConfig):
    """Configuration for running an ADK agent."""

    url: str = Field("https://api-agent-dev.thaink2.fr/api/adk/run", description="The API endpoint URL for the ADK agent.")
    agent_id: str = Field(..., description="The ID of the agent to run.")
    user_id: str = Field(..., description="The user's ID, typically an email.")
    message_text: str = Field(..., description="The text content of the message to send to the agent.")
    jwt_token: str = Field(..., description="The JWT token for authentication.")


class RefreshWebhooksConfig(BaseBlocConfig):
    """Configuration for refreshing webhooks."""

    url: str = Field(..., description="The API endpoint URL for refreshing webhooks.")
    jwt_token: str = Field(..., description="The JWT token for authentication.")
