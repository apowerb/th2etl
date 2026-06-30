from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SchedulerCreateModel(BaseModel):
    name: str = Field(..., description="The unique name of the scheduler.")
    pipeline_name: str = Field(..., description="The name of the pipeline to schedule.")
    trigger_name: str = Field(..., description="The name of the trigger to use for the schedule.")
    description: str | None = Field(None, description="An optional description of the scheduler.")
    variables: dict[str, Any] = Field(
        default_factory=dict,
        description="Runtime variables injected into the run context each time the schedule fires.",
    )
    active: bool = Field(True, description="Whether the schedule fires. Set False to create it disabled.")


class SchedulerUpdateModel(BaseModel):
    pipeline_name: str | None = Field(None, description="The name of the pipeline.")
    trigger_name: str | None = Field(None, description="The name of the trigger.")
    description: str | None = Field(None, description="The description of the scheduler.")
    variables: dict[str, Any] | None = Field(None, description="Replace the scheduler's runtime variables.")
    active: bool | None = Field(None, description="Enable/disable the schedule.")


class SchedulerVariablesModel(BaseModel):
    variables: dict[str, Any] = Field(
        default_factory=dict, description="The new runtime variables (replaces the previous set)."
    )


class SchedulerRunModel(BaseModel):
    variables: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional variables merged over the scheduler's stored variables for this ad-hoc run.",
    )
