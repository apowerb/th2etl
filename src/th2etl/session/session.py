from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Sequence


def build_isolated_env(extra_env: dict[str, str] | None = None) -> dict[str, str]:
    env = {}
    env["PYTHONUNBUFFERED"] = "1"
    env["PATH"] = os.environ.get("PATH", "")
    virtual_env = os.environ.get("VIRTUAL_ENV")
    if virtual_env:
        env["VIRTUAL_ENV"] = virtual_env
    env["PYTHONPATH"] = os.environ.get("PYTHONPATH", "")
    if extra_env:
        env.update(extra_env)
    return env


def run_in_isolated_session(command: Sequence[str], extra_env: dict[str, str] | None = None) -> subprocess.Popen[bytes]:
    env = build_isolated_env(extra_env)
    return subprocess.Popen(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def spawn_background_job(module_name: str, args: Sequence[str], extra_env: dict[str, str] | None = None) -> subprocess.Popen[bytes]:
    command = [sys.executable, "-m", module_name, *args]
    return run_in_isolated_session(command, extra_env=extra_env)
