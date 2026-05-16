from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from th2etl.storage import DatabaseStorage
from th2etl.configs.settings import get_settings

router = APIRouter()

def get_db():
    settings = get_settings()
    with DatabaseStorage.from_settings(settings) as db:
        yield db

class TriggerCreateModel(BaseModel):
    name: str = Field(..., description="The unique name of the trigger.")
    pipeline_name: str = Field(..., description="The name of the pipeline this trigger is for.")
    cron_expression: str = Field(..., description="The cron expression for the trigger schedule.")
    description: str | None = Field(None, description="An optional description of the trigger.")

class TriggerUpdateModel(BaseModel):
    pipeline_name: str | None = Field(None, description="The name of the pipeline.")
    cron_expression: str | None = Field(None, description="The cron expression for the schedule.")
    description: str | None = Field(None, description="The description of the trigger.")

@router.post("/", status_code=status.HTTP_201_CREATED)
def create_trigger(trigger: TriggerCreateModel, db: DatabaseStorage = Depends(get_db)):
    try:
        return db.create_trigger(
            name=trigger.name,
            pipeline_name=trigger.pipeline_name,
            cron_expression=trigger.cron_expression,
            description=trigger.description,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.get("/")
def list_triggers(db: DatabaseStorage = Depends(get_db)):
    return db.list_triggers()

@router.get("/{name}")
def get_trigger(name: str, db: DatabaseStorage = Depends(get_db)):
    trigger = db.get_trigger(name)
    if trigger is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trigger not found")
    return trigger

@router.put("/{name}")
def update_trigger(name: str, trigger: TriggerUpdateModel, db: DatabaseStorage = Depends(get_db)):
    try:
        return db.update_trigger(
            name=name,
            pipeline_name=trigger.pipeline_name,
            cron_expression=trigger.cron_expression,
            description=trigger.description,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_trigger(name: str, db: DatabaseStorage = Depends(get_db)):
    if not db.delete_trigger(name):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trigger not found")
