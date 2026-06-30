from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from th2etl.storage import DatabaseStorage
from th2etl.configs.settings import get_settings

router = APIRouter()


def get_db():
    settings = get_settings()
    with DatabaseStorage.from_settings(settings) as db:
        yield db


@router.get("/{run_id}")
def get_run(run_id: int, db: DatabaseStorage = Depends(get_db)):
    """Look up a run by id alone (across all pipelines)."""
    run = db.get_pipeline_run(run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return run


@router.post("/{run_id}/cancel")
def cancel_run(run_id: int, db: DatabaseStorage = Depends(get_db)):
    """Best-effort cancel: mark a non-terminal run as cancelled (the background
    worker is not interrupted, but the status reflects the cancellation)."""
    run = db.cancel_pipeline_run(run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return run
