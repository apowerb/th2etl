from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class BlocCreateModel(BaseModel):
    name: str = Field(..., description="The unique name of the bloc.")
    bloc_type: str = Field(..., description="The type of the bloc (e.g., csv_loader, script_bloc).")
    dependencies: list[str] | None = Field(None, description="A list of bloc names that this bloc depends on.")
    config: dict[str, Any] | None = Field(None, description="The configuration for the bloc.")
    description: str | None = Field(None, description="An optional description of the bloc.")


class BlocUpdateModel(BaseModel):
    bloc_type: str | None = Field(None, description="The type of the bloc.")
    dependencies: list[str] | None = Field(None, description="The list of dependencies.")
    config: dict[str, Any] | None = Field(None, description="The configuration for the bloc.")
    description: str | None = Field(None, description="The description of the bloc.")
