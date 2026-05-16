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

class PipelineCreateModel(BaseModel):
    name: str = Field(..., description="The unique name of the pipeline.")
    bloc_names: list[str] = Field(..., description="A list of bloc names included in the pipeline.")
    description: str | None = Field(None, description="An optional description of the pipeline.")

class PipelineUpdateModel(BaseModel):
    bloc_names: list[str] | None = Field(None, description="The list of bloc names in the pipeline.")
    description: str | None = Field(None, description="The description of the pipeline.")

@router.post("/", status_code=status.HTTP_201_CREATED)
def create_pipeline(pipeline: PipelineCreateModel, db: DatabaseStorage = Depends(get_db)):
    try:
        return db.create_pipeline(
            name=pipeline.name,
            bloc_names=pipeline.bloc_names,
            description=pipeline.description,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.get("/")
def list_pipelines(db: DatabaseStorage = Depends(get_db)):
    return db.list_pipelines()

@router.get("/{name}")
def get_pipeline(name: str, db: DatabaseStorage = Depends(get_db)):
    pipeline = db.get_pipeline(name)
    if pipeline is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline not found")
    return pipeline

@router.put("/{name}")
def update_pipeline(name: str, pipeline: PipelineUpdateModel, db: DatabaseStorage = Depends(get_db)):
    try:
        return db.update_pipeline(
            name=name,
            bloc_names=pipeline.bloc_names,
            description=pipeline.description,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_pipeline(name: str, db: DatabaseStorage = Depends(get_db)):
    if not db.delete_pipeline(name):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline not found")
