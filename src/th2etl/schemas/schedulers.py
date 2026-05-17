from __future__ import annotations

from pydantic import BaseModel, Field


class SchedulerCreateModel(BaseModel):
    name: str = Field(..., description="The unique name of the scheduler.")
    pipeline_name: str = Field(..., description="The name of the pipeline to schedule.")
    trigger_name: str = Field(..., description="The name of the trigger to use for the schedule.")
    description: str | None = Field(None, description="An optional description of the scheduler.")


class SchedulerUpdateModel(BaseModel):
    pipeline_name: str | None = Field(None, description="The name of the pipeline.")
    trigger_name: str | None = Field(None, description="The name of the trigger.")
    description: str | None = Field(None, description="The description of the scheduler.")
