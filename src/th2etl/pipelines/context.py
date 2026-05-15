from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class RunContext:
    """Provides details about the current pipeline run."""

    scheduler_name: str | None = None
    trigger_name: str | None = None
    scheduled_at: datetime | None = None
    output_dir: Path | None = None

    # Arbitrary storage for passing data between blocs
    context_vars: dict[str, Any] = field(default_factory=dict)
