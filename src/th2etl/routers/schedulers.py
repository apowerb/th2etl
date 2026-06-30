from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from th2etl.storage import DatabaseStorage
from th2etl.storage.database import SchedulerRecord
from th2etl.configs.settings import get_settings
from th2etl.pipelines.runner import execute_pipeline_run
from th2etl.schemas.schedulers import (
    SchedulerCreateModel,
    SchedulerRunModel,
    SchedulerUpdateModel,
    SchedulerVariablesModel,
)

router = APIRouter()


def get_db():
    settings = get_settings()
    with DatabaseStorage.from_settings(settings) as db:
        yield db


def _public(scheduler: SchedulerRecord) -> dict:
    """Serialize a scheduler WITHOUT its runtime variables: those hold secrets
    (JWT tokens) and are write-only via the API — never returned by reads."""
    data = asdict(scheduler)
    data.pop("variables", None)
    return data


@router.post("/", status_code=status.HTTP_201_CREATED)
def create_scheduler(scheduler: SchedulerCreateModel, db: DatabaseStorage = Depends(get_db)):
    try:
        return _public(db.create_scheduler(
            name=scheduler.name,
            pipeline_name=scheduler.pipeline_name,
            trigger_name=scheduler.trigger_name,
            description=scheduler.description,
            variables=scheduler.variables,
            active=scheduler.active,
        ))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/")
def list_schedulers(db: DatabaseStorage = Depends(get_db)):
    return [_public(s) for s in db.list_schedulers()]


@router.get("/{name}")
def get_scheduler(name: str, db: DatabaseStorage = Depends(get_db)):
    scheduler = db.get_scheduler(name)
    if scheduler is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scheduler not found")
    return _public(scheduler)


@router.put("/{name}")
def update_scheduler(name: str, scheduler: SchedulerUpdateModel, db: DatabaseStorage = Depends(get_db)):
    try:
        return _public(db.update_scheduler(
            name=name,
            pipeline_name=scheduler.pipeline_name,
            trigger_name=scheduler.trigger_name,
            description=scheduler.description,
            variables=scheduler.variables,
            active=scheduler.active,
        ))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.put("/{name}/variables")
def update_scheduler_variables(name: str, body: SchedulerVariablesModel, db: DatabaseStorage = Depends(get_db)):
    """Replace a scheduler's runtime variables (e.g. for token rotation)."""
    try:
        return _public(db.update_scheduler_variables(name=name, variables=body.variables))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/{name}/run", status_code=status.HTTP_202_ACCEPTED)
def run_scheduler_now(
    name: str,
    body: SchedulerRunModel,
    background_tasks: BackgroundTasks,
    db: DatabaseStorage = Depends(get_db),
):
    """Trigger the scheduler's pipeline ad-hoc, using its stored variables
    merged with any variables provided in the request body."""
    scheduler = db.get_scheduler(name)
    if scheduler is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scheduler not found")

    merged = {**scheduler.variables, **body.variables}
    run = db.create_pipeline_run(pipeline_name=scheduler.pipeline_name, variables=merged)
    background_tasks.add_task(execute_pipeline_run, run.id, scheduler.pipeline_name, merged)
    return {"run_id": run.id, "pipeline_name": scheduler.pipeline_name, "status": run.status}


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_scheduler(name: str, db: DatabaseStorage = Depends(get_db)):
    if not db.delete_scheduler(name):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scheduler not found")
