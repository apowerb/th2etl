#!/usr/bin/env bash
# Writes the release version into pyproject.toml AND uv.lock, in place.
#
# Both files, together. The PyPI job already rewrites pyproject.toml so the
# wheel carries the tag; the Docker image is built from the same source and
# would otherwise report the placeholder 0.0.1 under a 0.0.12 tag -- the exact
# mismatch that made th2pulse 0.1.2 unreadable after the fact. And uv.lock
# records the project version too, so rewriting pyproject.toml alone makes
# `uv sync --frozen` refuse the build with "the lockfile is not up-to-date".
#
# Usage: VERSION=0.0.12 .github/scripts/stamp-release-version.sh
set -euo pipefail

: "${VERSION:?VERSION is required, e.g. 0.0.12}"

python3 - "$VERSION" <<'PY'
import pathlib, re, sys

version = sys.argv[1]

pyproject = pathlib.Path("pyproject.toml")
text, count = re.subn(r"(?m)^version = \"[^\"]*\"$", f'version = "{version}"', pyproject.read_text(), count=1)
if count != 1:
    raise SystemExit("pyproject.toml: no top-level `version = \"...\"` line to rewrite")
pyproject.write_text(text)

lock = pathlib.Path("uv.lock")
text, count = re.subn(
    r"(\[\[package\]\]\nname = \"th2etl\"\nversion = )\"[^\"]*\"",
    lambda m: m.group(1) + f'"{version}"',
    lock.read_text(),
    count=1,
)
if count != 1:
    raise SystemExit("uv.lock: no th2etl package entry to rewrite")
lock.write_text(text)

print(f"stamped {version} into pyproject.toml and uv.lock")
PY
