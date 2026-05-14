from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Sequence


class BlocType(str, Enum):
    LOADER = "loader"
    TRANSFORMER = "transformer"
    EXPORTER = "exporter"


class Bloc(ABC):
    def __init__(self, name: str, dependencies: Sequence[str] | None = None) -> None:
        self.name = name
        self.dependencies = list(dependencies) if dependencies else []

    @property
    @abstractmethod
    def type(self) -> BlocType:
        ...

    @abstractmethod
    def execute(self, context: dict[str, Any]) -> None:
        ...


class LoaderBloc(Bloc):
    @property
    def type(self) -> BlocType:
        return BlocType.LOADER


class TransformerBloc(Bloc):
    @property
    def type(self) -> BlocType:
        return BlocType.TRANSFORMER


class ExporterBloc(Bloc):
    @property
    def type(self) -> BlocType:
        return BlocType.EXPORTER
