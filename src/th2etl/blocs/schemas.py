from __future__ import annotations

from typing import Annotated, Any, Literal
from pydantic import BaseModel, Field


class BaseBlocConfig(BaseModel):
    """Base schema for bloc configurations."""

    http_timeout: float = Field(
        30.0,
        gt=0,
        description="Timeout (seconds) for outbound HTTP calls made by the bloc. "
        "Prevents a hung upstream (e.g. th2agent) from leaving a run 'running' forever.",
    )

    class Config:
        extra = "allow"


class CsvLoaderConfig(BaseBlocConfig):
    """Configuration for loading data from a CSV file."""

    file_path: str = Field(..., description="The path to the CSV file to load.")
    delimiter: str = Field(",", description="The delimiter used in the CSV file.")


class PostgresLoaderConfig(BaseBlocConfig):
    """Configuration for loading data from a PostgreSQL database."""

    query: str = Field(..., description="The SQL query to execute to load the data.")


class PostgresExporterConfig(BaseBlocConfig):
    """Configuration for exporting data to a PostgreSQL table."""

    table_name: str = Field(..., description="The destination table name.")
    source_bloc: str = Field(..., description="Name of the bloc whose '{source_bloc}_data' is written.")
    db_schema: str | None = Field(None, description="Optional destination schema.")
    if_exists: Literal["fail", "replace", "append"] = Field(
        "replace", description="pandas to_sql behaviour when the table exists."
    )


class PdfLoaderConfig(BaseBlocConfig):
    """Configuration for extracting text from a PDF file."""

    file_path: str = Field(..., description="The path to the PDF file to load.")
    pages: list[Annotated[int, Field(ge=0)]] | None = Field(
        None,
        description="Optional 0-indexed subset of pages to extract. Extracts all pages when omitted.",
    )


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

    base_url: str = Field(..., description="The base URL of the ADK agent API (e.g., https://api-agent-dev.thaink2.fr). Environment-level (set per deployment).")
    # agent_id / user_id / message_text are resolved at run time from the run
    # variables (run_context.context_vars) and fall back to these static values
    # when not provided — so they are optional here.
    agent_id: str | None = Field(None, description="The ID of the agent to run. Usually supplied per run via the 'agent_id' run variable.")
    user_id: str | None = Field(None, description="The user's ID (JWT 'sub'). Usually supplied per run via the 'user_id' run variable.")
    message_text: str | None = Field(None, description="The message to send. Usually supplied per run via the 'message_text' run variable.")
    data: dict[str, Any] | None = Field(default_factory=dict, description="Optional data to pass to the agent. Can be overridden by the 'data' run variable.")
    run_mode: str = Field("run", description="The run mode for the agent.")
    streaming: bool = Field(False, description="Whether to use streaming mode.")


class RunAdkFromJwtConfig(BaseBlocConfig):
    """Configuration for running an ADK agent from a refresh JWT (faithful to
    the MageAI flow: forwards the token to /api/adk/run_from_jwt)."""

    base_url: str = Field(..., description="The base URL of the ADK agent API. Environment-level.")
    # jwt_token / agent_id / data normally arrive per run via run variables.
    jwt_token: str | None = Field(None, description="Agent refresh token. Usually supplied per run via the 'jwt_token' run variable.")
    agent_id: str | None = Field(None, description="Agent id, forwarded for token rotation. Usually a run variable.")
    data: dict[str, Any] | None = Field(default_factory=dict, description="Optional agent metadata (the 'agent_meta' run variable).")


class RefreshWebhooksConfig(BaseBlocConfig):
    """Configuration for refreshing webhooks."""

    url: str = Field(..., description="The API endpoint URL for refreshing webhooks.")
    user_id: str = Field(..., description="The user's ID, typically an email, used for the JWT 'sub' claim.")
