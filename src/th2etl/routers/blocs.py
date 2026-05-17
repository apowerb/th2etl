from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from th2etl.storage import DatabaseStorage
from th2etl.configs.settings import get_settings
from th2etl.schemas.blocs import BlocCreateModel, BlocUpdateModel

router = APIRouter()

def get_db():
    settings = get_settings()
    with DatabaseStorage.from_settings(settings) as db:
        yield db



@router.post("/", status_code=status.HTTP_201_CREATED)
def create_bloc(bloc: BlocCreateModel, db: DatabaseStorage = Depends(get_db)):
    try:
        return db.create_bloc(
            name=bloc.name,
            bloc_type=bloc.bloc_type,
            dependencies=bloc.dependencies,
            config=bloc.config,
            description=bloc.description,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.get("/")
def list_blocs(db: DatabaseStorage = Depends(get_db)):
    return db.list_blocs()

@router.get("/{name}")
def get_bloc(name: str, db: DatabaseStorage = Depends(get_db)):
    bloc = db.get_bloc(name)
    if bloc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bloc not found")
    return bloc

@router.put("/{name}")
def update_bloc(name: str, bloc: BlocUpdateModel, db: DatabaseStorage = Depends(get_db)):
    try:
        return db.update_bloc(
            name=name,
            bloc_type=bloc.bloc_type,
            dependencies=bloc.dependencies,
            config=bloc.config,
            description=bloc.description,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_bloc(name: str, db: DatabaseStorage = Depends(get_db)):
    if not db.delete_bloc(name):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bloc not found")
