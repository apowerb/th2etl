from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from th2etl.storage import DatabaseStorage
from th2etl.configs.settings import get_settings
from th2etl.schemas.schedulers import SchedulerCreateModel, SchedulerUpdateModel

router = APIRouter()

def get_db():
    settings = get_settings()
    with DatabaseStorage.from_settings(settings) as db:
        yield db



@router.post("/", status_code=status.HTTP_201_CREATED)
def create_scheduler(scheduler: SchedulerCreateModel, db: DatabaseStorage = Depends(get_db)):
    try:
        return db.create_scheduler(
            name=scheduler.name,
            pipeline_name=scheduler.pipeline_name,
            trigger_name=scheduler.trigger_name,
            description=scheduler.description,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.get("/")
def list_schedulers(db: DatabaseStorage = Depends(get_db)):
    return db.list_schedulers()

@router.get("/{name}")
def get_scheduler(name: str, db: DatabaseStorage = Depends(get_db)):
    scheduler = db.get_scheduler(name)
    if scheduler is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scheduler not found")
    return scheduler

@router.put("/{name}")
def update_scheduler(name: str, scheduler: SchedulerUpdateModel, db: DatabaseStorage = Depends(get_db)):
    try:
        return db.update_scheduler(
            name=name,
            pipeline_name=scheduler.pipeline_name,
            trigger_name=scheduler.trigger_name,
            description=scheduler.description,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_scheduler(name: str, db: DatabaseStorage = Depends(get_db)):
    if not db.delete_scheduler(name):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scheduler not found")
