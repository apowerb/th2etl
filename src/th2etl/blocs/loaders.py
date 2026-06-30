from __future__ import annotations

import logging
import csv
from typing import Any

import pypdf
import requests
from pypdf import PdfReader

from th2etl.blocs.base import LoaderBloc
from th2etl.pipelines.context import RunContext
from th2etl.blocs.schemas import (
    CsvLoaderConfig,
    ApiLoaderConfig,
    PdfLoaderConfig,
)

logger = logging.getLogger(__name__)


class CsvLoaderBloc(LoaderBloc):
    """Loads data from a CSV file."""

    def __init__(
        self,
        name: str,
        config: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(name=name)
        self.config = CsvLoaderConfig(**(config or {}))

    def execute(self, run_context: RunContext) -> None:
        logger.info(f"Loading data from CSV file: {self.config.file_path}")
        try:
            with open(self.config.file_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f, delimiter=self.config.delimiter)
                rows = list(reader)
            run_context.context_vars[f"{self.name}_data"] = rows
            logger.info(f"Loaded {len(rows)} rows from {self.config.file_path}")
        except FileNotFoundError:
            logger.error(f"CSV file not found at: {self.config.file_path}")
            raise
        except Exception as e:
            logger.error(f"Failed to load data from {self.config.file_path}: {e}")
            raise


class PdfLoaderBloc(LoaderBloc):
    """Extracts text from a PDF file into the run context.

    Writes two context variables:
      - ``{name}_text``  : the full extracted text (pages joined by newlines)
      - ``{name}_pages`` : the per-page extracted text as a list of strings
    """

    def __init__(
        self,
        name: str,
        config: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(name=name)
        self.config = PdfLoaderConfig(**(config or {}))

    def execute(self, run_context: RunContext) -> None:
        logger.info(f"Extracting text from PDF file: {self.config.file_path}")
        try:
            reader = PdfReader(self.config.file_path)
            total_pages = len(reader.pages)
            if self.config.pages is None:
                indices = range(total_pages)
            else:
                indices = [p for p in self.config.pages if 0 <= p < total_pages]
            pages_text = [reader.pages[i].extract_text() or "" for i in indices]
        except FileNotFoundError:
            logger.error(f"PDF file not found at: {self.config.file_path}")
            raise
        except pypdf.errors.PyPdfError as e:
            logger.error(f"Failed to read PDF {self.config.file_path}: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to extract text from {self.config.file_path}: {e}")
            raise

        run_context.context_vars[f"{self.name}_pages"] = pages_text
        run_context.context_vars[f"{self.name}_text"] = "\n".join(pages_text)
        logger.info(f"Extracted text from {len(pages_text)} page(s) of {self.config.file_path}")


class ApiLoaderBloc(LoaderBloc):
    """Loads data from a web API."""

    def __init__(
        self,
        name: str,
        config: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(name=name)
        self.config = ApiLoaderConfig(**(config or {}))

    def execute(self, run_context: RunContext) -> None:
        logger.info(f"Fetching data from API: {self.config.method} {self.config.url}")
        try:
            response = requests.request(
                self.config.method,
                self.config.url,
                params=self.config.params,
                headers=self.config.headers,
                json=self.config.json_payload,
            )
            response.raise_for_status()
            data = response.json()
            
            if not isinstance(data, list):
                logger.warning("API response is not a list, wrapping it in a list.")
                data = [data]
            
            run_context.context_vars[f"{self.name}_data"] = data
            logger.info(f"Loaded {len(data)} records from API")
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch data from API: {e}")
            raise
