from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PipelineRunRequest(BaseModel):
    variables: dict[str, Any] = Field(
        default_factory=dict,
        description="Runtime variables passed into the pipeline run context.",
    )


class PipelineCreateModel(BaseModel):
    name: str = Field(..., description="The unique name of the pipeline.")
    stages: list[list[str]] = Field(..., description="A list of stages, where each stage is a list of bloc names to be executed in parallel.")
    description: str | None = Field(None, description="An optional description of the pipeline.")


class PipelineUpdateModel(BaseModel):
    stages: list[list[str]] | None = Field(None, description="The stages of the pipeline.")
    description: str | None = Field(None, description="The description of the pipeline.")
