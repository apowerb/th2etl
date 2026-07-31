"""Authentication for incoming calls to the th2etl API.

The ``api_key`` setting already existed and was set in production, but
nothing read it: the orchestration API answered anyone. This module wires
it up.

The key protects the business routes. ``/`` and ``/health`` stay open: an
availability probe should not need a secret.
"""
from __future__ import annotations

import logging
import secrets

from fastapi import Header, HTTPException, status

from th2etl.configs.settings import get_settings

logger = logging.getLogger(__name__)

PREFIX = "Bearer "


def require_api_key(authorization: str | None = Header(default=None)) -> None:
    """Reject the request if the header does not carry the expected key."""
    expected = (get_settings().api_key or "").strip()

    # An empty string satisfies pydantic validation (`api_key: str` accepts
    # ""), which would leave the API open to anyone with no error to signal
    # it. We refuse instead, and log it.
    if not expected:
        logger.error(
            "[AUTH] API_KEY is empty: all business routes are refused. "
            "Set API_KEY to reopen the service."
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication not configured: set API_KEY.",
        )

    if not authorization or not authorization.startswith(PREFIX):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    provided = authorization[len(PREFIX):].strip()

    # Constant-time comparison: `==` stops at the first differing character
    # and would let the key be guessed one measurement at a time.
    if not secrets.compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
            headers={"WWW-Authenticate": "Bearer"},
        )
