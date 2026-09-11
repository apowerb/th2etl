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

# perl-base est un paquet Essential de l'image de base python:3.11-slim-trixie :
# rien au-dessus ne le tire, et cette image n'installe aucun paquet systeme.
# Il porte a lui seul les trois dernieres vulnerabilites critiques de l'image --
# CVE-2026-13221, CVE-2026-42496, CVE-2026-8376 -- sans correctif publie pour
# cette version de Debian. Un service Python pur ne l'execute jamais : le CMD
# est `python -m th2etl`, et ni uv ni le paquet installe n'appellent perl.
#
# Consequence pour qui etend cette image (FROM apowerb/th2etl) : `apt-get
# install` continue de fonctionner pour les paquets ordinaires -- dpkg et apt
# n'ont pas besoin de perl -- et un paquet dont les scripts de maintenance sont
# ecrits en Perl le reinstallera automatiquement comme n'importe quelle
# dependance manquante. Aucun etat durablement casse : au pire une image
# derivee un peu plus grosse.
#
# Le coeur apowerb applique la meme purge, avec la meme justification, et se
# mesure a zero critique.
RUN apt-get update \
    && apt-get purge -y --allow-remove-essential perl-base \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# Meme raisonnement, meme image de base, cette fois pour util-linux et les
# paquets construits depuis la meme source (mount, login, bsdutils). Ils
# portent quatre avis HIGH -- CVE-2026-76642, -78408, -78409, -78410 -- sur des
# aides de montage qui tournent des post-hooks privilegies, sur
# `nsenter --join-cgroup` et sur la resolution de chemins X-mount. Ce service
# n'execute rien de tout cela : le CMD est du Python pur, et ni uv ni le paquet
# installe n'appellent mount, login, su ou nsenter.
#
# `apt-get autoremove` emporte ensuite libblkid1, libmount1, libsmartcols1 et
# liblastlog2-2, devenus orphelins. libuuid1 reste, et les avis continueront de
# lui etre attribues : un scanner rattache une CVE de source a tous les paquets
# binaires qui en sortent, mais le code vulnerable -- les aides de montage --
# est parti avec les binaires ci-dessus.
#
# Le coeur apowerb applique exactement cette purge (PR #137), mesuree a
# 49 avis HIGH contre 15.
RUN apt-get update \
    && apt-get purge -y --allow-remove-essential util-linux mount login bsdutils \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# pip et setuptools ne servent jamais a l'execution : le service tourne dans
# /opt/venv, construit par uv, qui n'en embarque aucun des deux. Les copies de
# l'image de base vendorisent leur propre arbre de dependances sous
# `setuptools/_vendor/`, et c'est CET arbre -- pas les dependances de
# l'application -- que visent les avis `wheel` (CVE-2026-24049) et
# `jaraco.context` (CVE-2026-23949) releves sur l'image. Les retirer les retire.
#
# Pour qui etend cette image : `pip` n'est plus la. Utiliser uv, deja present
# dans /bin, ou lancer `python -m ensurepip` d'abord.
#
# Le coeur apowerb fait la meme chose (PR #137).
RUN /usr/local/bin/python -m pip uninstall -y pip setuptools \
    && rm -rf /usr/local/lib/python3.11/site-packages/pip* \
              /usr/local/lib/python3.11/site-packages/setuptools* \
              /usr/local/lib/python3.11/site-packages/pkg_resources \
              /usr/local/lib/python3.11/site-packages/_distutils_hack \
              /usr/local/lib/python3.11/site-packages/distutils-precedence.pth \
              /usr/local/lib/python3.11/site-packages/wheel*

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
