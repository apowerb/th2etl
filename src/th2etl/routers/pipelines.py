from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from th2etl.storage import DatabaseStorage
from th2etl.configs.settings import get_settings
from th2etl.pipelines.runner import execute_pipeline_run
from th2etl.schemas.pipelines import (
    PipelineCreateModel,
    PipelineRunRequest,
    PipelineUpdateModel,
)

router = APIRouter()

def get_db():
    settings = get_settings()
    with DatabaseStorage.from_settings(settings) as db:
        yield db



@router.post("/", status_code=status.HTTP_201_CREATED)
def create_pipeline(pipeline: PipelineCreateModel, db: DatabaseStorage = Depends(get_db)):
    try:
        return db.create_pipeline(
            name=pipeline.name,
            stages=pipeline.stages,
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
            stages=pipeline.stages,
            description=pipeline.description,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_pipeline(name: str, db: DatabaseStorage = Depends(get_db)):
    if not db.delete_pipeline(name):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline not found")


@router.post("/{name}/run", status_code=status.HTTP_202_ACCEPTED)
def run_pipeline(
    name: str,
    request: PipelineRunRequest,
    background_tasks: BackgroundTasks,
    db: DatabaseStorage = Depends(get_db),
):
    """Trigger an ad-hoc run of a pipeline with runtime variables.

    Creates a run record (status=pending), schedules execution in the
    background, and returns immediately so the caller can poll the run.
    """
    if db.get_pipeline(name) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline not found")

    run = db.create_pipeline_run(pipeline_name=name, variables=request.variables)
    background_tasks.add_task(execute_pipeline_run, run.id, name, request.variables)
    return {"run_id": run.id, "pipeline_name": name, "status": run.status}


@router.get("/{name}/runs")
def list_pipeline_runs(name: str, db: DatabaseStorage = Depends(get_db)):
    if db.get_pipeline(name) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline not found")
    return db.list_pipeline_runs(name)


@router.get("/{name}/runs/{run_id}")
def get_pipeline_run(name: str, run_id: int, db: DatabaseStorage = Depends(get_db)):
    run = db.get_pipeline_run(run_id)
    if run is None or run.pipeline_name != name:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return run
