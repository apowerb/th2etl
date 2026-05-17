from __future__ import annotations

from pydantic import BaseModel, Field


class PipelineCreateModel(BaseModel):
    name: str = Field(..., description="The unique name of the pipeline.")
    stages: list[list[str]] = Field(..., description="A list of stages, where each stage is a list of bloc names to be executed in parallel.")
    description: str | None = Field(None, description="An optional description of the pipeline.")


class PipelineUpdateModel(BaseModel):
    stages: list[list[str]] | None = Field(None, description="The stages of the pipeline.")
    description: str | None = Field(None, description="The description of the pipeline.")
