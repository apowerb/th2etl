"""The orchestration API only answers whoever presents the key."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from th2etl.helpers.api_auth import require_api_key

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "src" / "th2etl" / "main.py"

# The business routes: those that list, trigger, and modify.
PROTECTED_ROUTERS = ["blocs", "pipelines", "triggers", "schedulers", "runs"]


@pytest.fixture
def app_with_key(monkeypatch):
    """Build an app carrying the same dependency as the real API.

    monkeypatch, not a manual substitution: the previous version of this
    file replaced get_settings in the authentication module without
    restoring it, and made 17 tests in other files fail.
    """

    def _build(key):
        class Fake:
            api_key = key

        monkeypatch.setattr("th2etl.helpers.api_auth.get_settings", lambda: Fake())

        app = FastAPI()

        @app.get("/protected", dependencies=[Depends(require_api_key)])
        def protected():
            return {"ok": True}

        @app.get("/health")
        def health():
            return {"status": "ok"}

        return TestClient(app, raise_server_exceptions=False)

    return _build


def test_without_key_the_business_route_is_refused(app_with_key):
    client = app_with_key("expected-secret")
    assert client.get("/protected").status_code == 401


def test_wrong_key_refused(app_with_key):
    client = app_with_key("expected-secret")
    r = client.get("/protected", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401


def test_scheme_other_than_bearer_refused(app_with_key):
    client = app_with_key("expected-secret")
    r = client.get("/protected", headers={"Authorization": "Basic expected-secret"})
    assert r.status_code == 401


def test_correct_key_accepted(app_with_key):
    client = app_with_key("expected-secret")
    r = client.get("/protected", headers={"Authorization": "Bearer expected-secret"})
    assert r.status_code == 200


def test_empty_key_closes_the_service_instead_of_opening_it(app_with_key):
    """The trap: `api_key: str` accepts "" and would silently open everything."""
    client = app_with_key("")
    r = client.get("/protected", headers={"Authorization": "Bearer whatever"})
    assert r.status_code == 503, "an empty key must close the service, never open it"


def test_health_stays_open(app_with_key):
    client = app_with_key("expected-secret")
    assert client.get("/health").status_code == 200


@pytest.mark.parametrize("router", PROTECTED_ROUTERS)
def test_each_business_router_carries_the_dependency(router):
    """Anti-regression: a router mounted without a guard fails the tests.

    We re-read the source of main.py rather than the app object: inspecting
    the app would not reveal whether a guard was removed from a single
    router.
    """
    tree = ast.parse(MAIN.read_text(encoding="utf-8"))
    unguarded = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        if not (isinstance(f, ast.Attribute) and f.attr == "include_router"):
            continue
        if not node.args:
            continue
        first = node.args[0]
        name = first.value.id if isinstance(first, ast.Attribute) else None
        if name != router:
            continue
        if not any(k.arg == "dependencies" for k in node.keywords):
            unguarded.append(name)

    assert not unguarded, f"router mounted without authentication: {unguarded}"
