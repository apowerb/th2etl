"""Idempotent seed for the pipelines th2agent expects from the orchestrator
(replacing MageAI): ``agents`` and ``process_pdf``.

WARNING — the bloc configs below are PLACEHOLDERS. The ADK ``base_url`` /
``agent_id`` / ``user_id`` and the PDF ``file_path`` must be set to real
values (and, ideally, fed from run variables once blocs read them from the
run context). This seed creates the STRUCTURE; the values need a review pass.

DEPENDENCY — ``process_pdf`` is NOT executable until the ``pdf_loader`` bloc
factory is registered, which ships in the feat/pdf-loader-bloc PR (#3). Seeding
before that PR is merged creates a pipeline that fails at build time with
``No registered bloc factory for bloc_type='pdf_loader'``. ``agents`` works on
its own.

CONCURRENCY — not safe to run concurrently: ``get`` then ``create`` is not
atomic, so two simultaneous runs can hit a UNIQUE violation. Run it once.

Run it against a live th2etl database with:

    python -m th2etl.seeds.default_pipelines
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Placeholders — set these to real values before going live (don't ship the
# DEV URL by accident: keep it an explicit REPLACE_ME so it can't be missed).
DEFAULT_AGENT_BASE_URL = "REPLACE_ME_BASE_URL"
PLACEHOLDER = "REPLACE_ME"

SEED_BLOCS: list[dict[str, Any]] = [
    {
        "name": "agents_runner",
        "bloc_type": "run_adk_agents",
        "config": {
            "base_url": DEFAULT_AGENT_BASE_URL,
            "agent_id": PLACEHOLDER,
            "user_id": PLACEHOLDER,
            "message_text": PLACEHOLDER,
        },
        "description": "Runs an ADK agent (equivalent of the MageAI 'agents' pipeline).",
    },
    {
        "name": "pdf_extract",
        "bloc_type": "pdf_loader",
        "config": {"file_path": PLACEHOLDER},
        "description": "Extracts text from a PDF into the run context.",
    },
    {
        "name": "pdf_agent",
        "bloc_type": "run_adk_agents",
        "config": {
            "base_url": DEFAULT_AGENT_BASE_URL,
            "agent_id": PLACEHOLDER,
            "user_id": PLACEHOLDER,
            "message_text": PLACEHOLDER,
        },
        "description": "Sends the extracted PDF text to an ADK agent.",
    },
]

SEED_PIPELINES: list[dict[str, Any]] = [
    {
        "name": "agents",
        "stages": [["agents_runner"]],
        "description": "Replaces the MageAI 'agents' pipeline.",
    },
    {
        "name": "process_pdf",
        "stages": [["pdf_extract"], ["pdf_agent"]],
        "description": "Replaces the MageAI 'process_pdf' pipeline: extract text then run an agent.",
    },
]


def seed_default_pipelines(storage: Any) -> dict[str, list[str]]:
    """Create the default blocs and pipelines if they don't already exist.

    Idempotent: existing blocs/pipelines are left untouched. Blocs are created
    before pipelines so the pipeline's bloc references resolve.
    """
    summary: dict[str, list[str]] = {
        "blocs_created": [],
        "blocs_skipped": [],
        "pipelines_created": [],
        "pipelines_skipped": [],
    }

    for spec in SEED_BLOCS:
        if storage.get_bloc(spec["name"]) is None:
            storage.create_bloc(
                name=spec["name"],
                bloc_type=spec["bloc_type"],
                config=spec["config"],
                description=spec.get("description"),
            )
            summary["blocs_created"].append(spec["name"])
            logger.info("Seeded bloc %s", spec["name"])
        else:
            summary["blocs_skipped"].append(spec["name"])

    for spec in SEED_PIPELINES:
        if storage.get_pipeline(spec["name"]) is None:
            storage.create_pipeline(
                name=spec["name"],
                stages=spec["stages"],
                description=spec.get("description"),
            )
            summary["pipelines_created"].append(spec["name"])
            logger.info("Seeded pipeline %s", spec["name"])
        else:
            summary["pipelines_skipped"].append(spec["name"])

    return summary


def main() -> None:
    from th2etl.configs.settings import get_settings
    from th2etl.storage import DatabaseStorage

    logging.basicConfig(level=logging.INFO)
    with DatabaseStorage.from_settings(get_settings()) as storage:
        summary = seed_default_pipelines(storage)
    print(summary)


if __name__ == "__main__":
    main()
