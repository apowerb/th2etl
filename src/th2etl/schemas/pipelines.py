from __future__ import annotations

from pydantic import BaseModel, Field


class PipelineCreateModel(BaseModel):
    name: str = Field(..., description="The unique name of the pipeline.")
    bloc_names: list[str] = Field(..., description="A list of bloc names included in the pipeline.")
    description: str | None = Field(None, description="An optional description of the pipeline.")


class PipelineUpdateModel(BaseModel):
    bloc_names: list[str] | None = Field(None, description="The list of bloc names in the pipeline.")
    description: str | None = Field(None, description="The description of the pipeline.")
