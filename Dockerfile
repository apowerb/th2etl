# th2etl service image.
#
# What this image must satisfy, and did not before: `docker run` on it starts
# the service. The previous image resolved its Python environment at every
# container start (`uv run` as CMD), so it needed network access from the
# running container, and the resolution it attempted failed anyway because the
# build context copied no README.md while pyproject declares one -- the
# editable build of the project exited 1. Every published tag (0.0.8 through
# 0.0.11 and latest) exits 1 on `docker run`, measured on 2026-09-04.
#
# The environment is therefore built HERE, once, and the CMD only runs it.
FROM python:3.11-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_NO_CACHE=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

# Dependencies first, from uv.lock, so a rebuild of the same tag resolves to
# the same transitive versions.
#
# The `postgres` extra is NOT optional here despite its name. `th2etl.blocs`
# imports `.postgresql` at package import time, which imports pandas, which
# only the extra installs -- so without it `python -m th2etl` dies on
# `ModuleNotFoundError: No module named pandas` before it reads a single
# setting. Measured on 2026-09-04 while proving this image starts.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --extra postgres --no-install-project

# Then the project itself. README.md is not documentation here: pyproject
# declares `readme = "README.md"`, so the build backend fails without it.
COPY README.md ./
COPY src ./src
COPY datasets ./datasets
RUN uv sync --frozen --no-dev --extra postgres --no-editable

EXPOSE 8000

# Plain `python`, not `uv run`: `uv run` re-resolves the project environment on
# every container start, which needs network access from the running container
# and pulls the dev dependency group into a production image.
#
# `--serve-api` ALONE, and that is not an omission. The FastAPI app already
# starts a SchedulerManager in its lifespan (src/th2etl/main.py), so adding
# `--run-scheduler` starts a SECOND, independent scheduler in another process:
# every cron trigger fires twice, and on a virgin database the two processes
# race each other inside CREATE TABLE -- measured, the API died on
# `UniqueViolation ... (typname)=(etl_blocs)` while the scheduler process kept
# the container "running", so nothing restarted it and the API was simply
# absent until someone restarted it by hand.
CMD ["python", "-m", "th2etl", "--serve-api", "--host", "0.0.0.0", "--port", "8000"]
