"""Tests for PdfLoaderBloc: extracting text from a PDF into the run context.

Uses a small real PDF fixture (tests/fixtures/sample.pdf) so extraction is
exercised end-to-end through pypdf, with no network or database.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from th2etl.blocs.loaders import PdfLoaderBloc
from th2etl.pipelines.context import RunContext

FIXTURE = str(Path(__file__).parent / "fixtures" / "sample.pdf")


def test_extracts_full_text_and_pages():
    bloc = PdfLoaderBloc(name="pdf", config={"file_path": FIXTURE})
    ctx = RunContext()
    bloc.execute(ctx)

    assert "th2etl pdf extraction works" in ctx.context_vars["pdf_text"]
    assert "page two content" in ctx.context_vars["pdf_text"]
    # the fixture has two pages
    assert len(ctx.context_vars["pdf_pages"]) == 2


def test_page_subset_is_respected():
    bloc = PdfLoaderBloc(name="pdf", config={"file_path": FIXTURE, "pages": [1]})
    ctx = RunContext()
    bloc.execute(ctx)

    assert len(ctx.context_vars["pdf_pages"]) == 1
    assert "page two content" in ctx.context_vars["pdf_text"]
    assert "th2etl pdf extraction works" not in ctx.context_vars["pdf_text"]


def test_out_of_range_pages_are_ignored():
    bloc = PdfLoaderBloc(name="pdf", config={"file_path": FIXTURE, "pages": [0, 99]})
    ctx = RunContext()
    bloc.execute(ctx)

    assert len(ctx.context_vars["pdf_pages"]) == 1


def test_missing_file_raises():
    bloc = PdfLoaderBloc(name="pdf", config={"file_path": "/no/such/file.pdf"})
    with pytest.raises(FileNotFoundError):
        bloc.execute(RunContext())


def test_registered_as_bloc_factory():
    from th2etl.pipelines.pipeline import build_bloc_from_record

    bloc = build_bloc_from_record("pdf", "pdf_loader", {"file_path": FIXTURE})
    assert isinstance(bloc, PdfLoaderBloc)
