# th2etl service image, built from the PUBLISHED wheel rather than the working
# tree, on the model of apowerb/th2pulse.
#
# Why the wheel: the PyPI workflow rewrites pyproject.toml's placeholder
# version (0.0.1) in flight, for the wheel only. A source build therefore has
# to stamp the version a second time or it reports the placeholder under
# whatever tag it is published as. Installing "th2etl==<tag>" is what makes
# the version the image reports the version it actually contains, with no
# second stamping to keep in step -- and the smoke test in
# .github/scripts/smoke-test-image.sh refuses any mismatch.
#
# What this image must satisfy, and did not before 2026-09-04: `docker run` on
# it starts the service. The environment is built HERE, once, and the CMD only
# runs it.
FROM python:3.11-slim-trixie

# Release to install. The Docker workflow passes it as a build-arg, derived
# from the git tag the PyPI workflow just published. There is deliberately no
# default: a build with no --build-arg fails loudly below rather than silently
# producing an image of whatever version PyPI happens to serve.
#
# To try the working tree instead of a release, run the service directly --
# `uv run --extra postgres python -m th2etl --serve-api`. This image is for
# published versions only.
ARG TH2ETL_VERSION

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_NO_CACHE=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

# Dependencies first, from uv.lock, so the two published architectures and any
# later rebuild of the same tag get the same transitive versions.
#
# The `postgres` extra is NOT optional here despite its name. `th2etl.blocs`
# imports `.postgresql` at package import time, which imports pandas, which
# only the extra installs -- so without it `python -m th2etl` dies on
# `ModuleNotFoundError: No module named pandas` before it reads a single
# setting. Measured on 2026-09-04 while proving this image starts.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --extra postgres --no-install-project

# Then the package itself, from PyPI at the tagged version. Nothing else from
# the working tree is needed at runtime: README.md only mattered to the source
# build, and datasets/ is used by the example notebook alone.
RUN test -n "${TH2ETL_VERSION}" \
    || { echo "TH2ETL_VERSION build-arg is required, e.g. --build-arg TH2ETL_VERSION=0.0.12" >&2; exit 1; } \
    && uv pip install --no-cache-dir "th2etl[postgres]==${TH2ETL_VERSION}"

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
