from __future__ import annotations

from fastapi import FastAPI, Depends, HTTPException, status
from th2etl.routers import blocs, pipelines, schedulers, triggers
from th2etl.storage import DatabaseStorage
from th2etl.configs.settings import get_settings

app = FastAPI(
    title="th2etl API",
    description="An API for managing ETL pipelines, blocs, triggers, and schedulers.",
    version="0.1.0",
)

def get_db():
    settings = get_settings()
    with DatabaseStorage.from_settings(settings) as db:
        yield db

app.include_router(blocs.router, prefix="/blocs", tags=["blocs"])
app.include_router(pipelines.router, prefix="/pipelines", tags=["pipelines"])
app.include_router(triggers.router, prefix="/triggers", tags=["triggers"])
app.include_router(schedulers.router, prefix="/schedulers", tags=["schedulers"])

@app.get("/", tags=["root"])
def read_root():
    return {"message": "Welcome to the th2etl API"}

@app.get("/health", tags=["health"])
def health_check(db: DatabaseStorage = Depends(get_db)):
    """Checks the health of the service, including the database connection."""
    if not db.check_connection():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection failed",
        )
    return {"status": "ok"}
