#!/usr/bin/env bash
# Runs a freshly built image and asserts it does what its tag claims.
#
# Why this exists: nothing in this pipeline ever ran the image it publishes.
# The only success criterion was "the build completed", and on 2026-09-04
# every published tag -- 0.0.8, 0.0.9, 0.0.10, 0.0.11 and latest -- exited 1
# on a plain `docker run`. Two defects, both of which a single run catches:
# the CMD was `uv run`, which re-resolves the environment at every container
# start (so the service needed PyPI reachable from inside the container), and
# the build context copied no README.md while pyproject.toml declares one, so
# that resolution failed anyway.
#
# Run it against a local build of a version that is on PyPI:
#   docker build --build-arg TH2ETL_VERSION=0.0.12 -t th2etl:smoke .
#   IMAGE=th2etl:smoke EXPECTED_VERSION=0.0.12 \
#     DB_DSN_HOST=127.0.0.1 DB_PORT=5432 DB_NAME=smoke DB_USER=postgres \
#     DB_PASSWORD=smoke .github/scripts/smoke-test-image.sh
#
# Required: IMAGE, EXPECTED_VERSION
# Optional: DB_* (all of them) -- when set, the image is also started against
#           that database and required to serve.
#           HOST_PORT -- the host port the container is reached on. It runs
#           with --network host, so this port is taken on the MACHINE running
#           the script, not inside a container. The default is deliberately
#           not 8000: that is apowerb's own default port, and squatting it on
#           a developer machine either fails the test for the wrong reason or
#           disturbs whatever was already there. A CI runner has neither
#           problem, a laptop does.
set -euo pipefail

: "${IMAGE:?IMAGE is required}"
: "${EXPECTED_VERSION:?EXPECTED_VERSION is required}"

fail() { echo "::error::$*" >&2; exit 1; }

HOST_PORT="${HOST_PORT:-18000}"

# Generated, not the literal it used to be. `smoketoken` was harmless in a
# runner and wrong everywhere else: with --network host the API below is
# reachable on the machine running this script for as long as the test lasts,
# and a key published in a public repository is not a key. One per run.
SMOKE_KEY="$( (openssl rand -hex 16 2>/dev/null) || date +%s%N )"

# 1. Everything the CMD imports resolves, offline, and the version matches the
#    tag. `--network none` is the assertion, not decoration: it is what tells
#    a baked environment apart from one resolved at container start.
#
#    pandas is in the list on purpose. It lives in the OPTIONAL `postgres`
#    extra, yet `th2etl.blocs` imports `.postgresql` at package import time --
#    so an image built without that extra dies before reading a setting.
echo "--- imports and version, with no network ---"
reported=$(docker run --rm --network none "$IMAGE" python -c \
  'import importlib.metadata, fastapi, uvicorn, pandas, psycopg; print(importlib.metadata.version("th2etl"))') \
  || fail "the image cannot import what its CMD needs, or needs network access to start"
[ "$reported" = "$EXPECTED_VERSION" ] \
  || fail "image reports th2etl ${reported} but is about to be published as ${EXPECTED_VERSION}"
echo "reports ${reported}, imports resolve offline."

if [ -z "${DB_NAME:-}" ]; then
  echo "--- DB_NAME unset, skipping the serving check ---"
  exit 0
fi

# 2. Against a VIRGIN database -- the state every first deployment is in, and
#    the only state in which the table creation path runs.
echo "--- serves its API on a fresh database ---"
container=$(docker run -d --network host \
  -e DATABASE_HOST="${DB_DSN_HOST:-127.0.0.1}" \
  -e DATABASE_PORT="${DB_PORT:-5432}" \
  -e DATABASE_NAME="$DB_NAME" \
  -e DATABASE_USER="${DB_USER:-postgres}" \
  -e DATABASE_PASSWORD="${DB_PASSWORD:-smoke}" \
  -e API_KEY="$SMOKE_KEY" \
  "$IMAGE" python -m th2etl --serve-api --host 0.0.0.0 --port "$HOST_PORT")
trap 'docker rm -f "$container" >/dev/null 2>&1 || true' EXIT

served=""
for attempt in $(seq 1 30); do
  if code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:${HOST_PORT}/openapi.json) \
     && [ "$code" = "200" ]; then
    served="yes"
    echo "/openapi.json answered 200 (attempt ${attempt}/30)."
    break
  fi
  sleep 2
done
[ -n "$served" ] || { echo "--- container logs ---" >&2; docker logs "$container" >&2 || true; fail "/openapi.json never answered 200"; }

# A container can be "running" with its API dead: the runner starts more than
# one process, and one of them surviving keeps the container up while the
# other is gone. Assert both, so that failure mode cannot pass.
state=$(docker inspect -f '{{.State.Status}}' "$container")
[ "$state" = "running" ] || fail "the container is ${state} after serving; something exited"

# 3. The API key is the only thing standing between this orchestrator and
#    anyone who can reach it. Both directions, so "it crashed" cannot pass for
#    "it refused".
echo "--- refuses a business route without the API key ---"
unauth=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:${HOST_PORT}/schedulers/)
[ "$unauth" = "401" ] || fail "GET /schedulers/ answered ${unauth} without a key, expected 401"
auth=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 \
  -H "Authorization: Bearer $SMOKE_KEY" http://127.0.0.1:${HOST_PORT}/schedulers/)
[ "$auth" = "200" ] || fail "GET /schedulers/ answered ${auth} with the right key, expected 200"
echo "401 without the key, 200 with it."
