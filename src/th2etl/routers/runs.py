from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, status

from th2etl.storage import DatabaseStorage
from th2etl.storage.database import RunRecord
from th2etl.configs.settings import get_settings

router = APIRouter()


def get_db():
    settings = get_settings()
    with DatabaseStorage.from_settings(settings) as db:
        yield db


def public_run(run: RunRecord) -> dict:
    """Serialize a run WITHOUT its ``variables`` — those carry secrets (JWT
    tokens) and must never be returned by reads."""
    data = asdict(run)
    data.pop("variables", None)
    return data


@router.get("/{run_id}")
def get_run(run_id: int, db: DatabaseStorage = Depends(get_db)):
    """Look up a run by id alone (across all pipelines)."""
    run = db.get_pipeline_run(run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return public_run(run)


@router.get("/{run_id}/logs")
def get_run_logs(run_id: int, limit: int = 500, db: DatabaseStorage = Depends(get_db)):
    """Return a run's structured execution log (events in order, oldest first) so
    the UI can surface the *flow* — worker started, each bloc, HTTP calls, status
    transitions — not just the terminal status. Safe to read: events carry no
    run variables (secrets), only lifecycle fields."""
    if db.get_pipeline_run(run_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return [asdict(log) for log in db.list_run_logs(run_id, limit=limit)]


@router.post("/{run_id}/cancel")
def cancel_run(run_id: int, db: DatabaseStorage = Depends(get_db)):
    """Best-effort cancel: mark a non-terminal run as cancelled (the background
    worker is not interrupted, but the status reflects the cancellation)."""
    run = db.cancel_pipeline_run(run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return public_run(run)
