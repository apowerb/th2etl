from __future__ import annotations

from pydantic import BaseModel, Field


class TriggerCreateModel(BaseModel):
    name: str = Field(..., description="The unique name of the trigger.")
    pipeline_name: str = Field(..., description="The name of the pipeline this trigger is for.")
    cron_expression: str = Field(..., description="The cron expression for the trigger schedule.")
    description: str | None = Field(None, description="An optional description of the trigger.")


class TriggerUpdateModel(BaseModel):
    pipeline_name: str | None = Field(None, description="The name of the pipeline.")
    cron_expression: str | None = Field(None, description="The cron expression for the schedule.")
    description: str | None = Field(None, description="The description of the trigger.")
