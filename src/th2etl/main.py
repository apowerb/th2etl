from __future__ import annotations

from contextlib import asynccontextmanager
import threading

from fastapi import FastAPI, Depends, HTTPException, status
from th2etl.routers import blocs, pipelines, schedulers, triggers
from th2etl.storage import DatabaseStorage
from th2etl.configs.settings import get_settings
from th2etl.scheduler.helpers import load_scheduler_manager

app_state = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handles startup and shutdown events for the FastAPI application."""
    print("Starting up the application and the background scheduler...")
    
    settings = get_settings()
    storage = DatabaseStorage.from_settings(settings)
    
    manager = load_scheduler_manager(storage, settings=settings)
    app_state["scheduler_manager"] = manager
    
    # Run the scheduler manager in a separate thread
    scheduler_thread = threading.Thread(target=manager.start, daemon=True)
    scheduler_thread.start()
    app_state["scheduler_thread"] = scheduler_thread
    
    yield
    
    print("Shutting down the application and the background scheduler...")
    manager.stop()
    scheduler_thread.join() # Wait for the thread to finish
    storage.close()


app = FastAPI(
    title="th2etl API",
    description="An API for managing ETL pipelines, blocs, triggers, and schedulers.",
    version="0.1.0",
    lifespan=lifespan,
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
    
    scheduler_manager = app_state.get("scheduler_manager")
    if not scheduler_manager or not app_state.get("scheduler_thread").is_alive():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Scheduler manager is not running",
        )
        
    return {"status": "ok", "scheduler_status": "running"}
