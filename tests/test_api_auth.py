"""L'API d'orchestration ne repond qu'a qui presente la cle."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from th2etl.helpers.api_auth import exiger_cle_api

RACINE = Path(__file__).resolve().parents[1]
MAIN = RACINE / "src" / "th2etl" / "main.py"

# Les routes metier : celles qui listent, declenchent et modifient.
ROUTEURS_PROTEGES = ["blocs", "pipelines", "triggers", "schedulers", "runs"]


@pytest.fixture
def app_avec_cle(monkeypatch):
    """Fabrique une app portant la meme dependance que l'API reelle.

    monkeypatch et non une substitution a la main : la version precedente de ce
    fichier remplacait get_settings dans le module d'authentification sans le
    restaurer, et faisait tomber 17 tests des autres fichiers.
    """

    def _fabrique(cle):
        class Faux:
            api_key = cle

        monkeypatch.setattr("th2etl.helpers.api_auth.get_settings", lambda: Faux())

        app = FastAPI()

        @app.get("/protege", dependencies=[Depends(exiger_cle_api)])
        def protege():
            return {"ok": True}

        @app.get("/health")
        def health():
            return {"status": "ok"}

        return TestClient(app, raise_server_exceptions=False)

    return _fabrique


def test_sans_cle_la_route_metier_est_refusee(app_avec_cle):
    client = app_avec_cle("secret-attendu")
    assert client.get("/protege").status_code == 401


def test_mauvaise_cle_refusee(app_avec_cle):
    client = app_avec_cle("secret-attendu")
    r = client.get("/protege", headers={"Authorization": "Bearer mauvaise"})
    assert r.status_code == 401


def test_schema_autre_que_bearer_refuse(app_avec_cle):
    client = app_avec_cle("secret-attendu")
    r = client.get("/protege", headers={"Authorization": "Basic secret-attendu"})
    assert r.status_code == 401


def test_bonne_cle_acceptee(app_avec_cle):
    client = app_avec_cle("secret-attendu")
    r = client.get("/protege", headers={"Authorization": "Bearer secret-attendu"})
    assert r.status_code == 200


def test_cle_vide_ferme_le_service_au_lieu_de_louvrir(app_avec_cle):
    """Le piege : `api_key: str` accepte "" et ouvrirait tout en silence."""
    client = app_avec_cle("")
    r = client.get("/protege", headers={"Authorization": "Bearer nimporte"})
    assert r.status_code == 503, "une cle vide doit fermer le service, jamais l'ouvrir"


def test_health_reste_ouverte(app_avec_cle):
    client = app_avec_cle("secret-attendu")
    assert client.get("/health").status_code == 200


@pytest.mark.parametrize("routeur", ROUTEURS_PROTEGES)
def test_chaque_routeur_metier_porte_la_dependance(routeur):
    """Anti-regression : un routeur monte sans garde fait echouer les tests.

    On relit la source de main.py plutot que l'objet app : inspecter l'app ne
    dirait pas si une garde a ete retiree d'un seul routeur.
    """
    arbre = ast.parse(MAIN.read_text(encoding="utf-8"))
    sans_garde = []

    for noeud in ast.walk(arbre):
        if not isinstance(noeud, ast.Call):
            continue
        f = noeud.func
        if not (isinstance(f, ast.Attribute) and f.attr == "include_router"):
            continue
        if not noeud.args:
            continue
        premier = noeud.args[0]
        nom = premier.value.id if isinstance(premier, ast.Attribute) else None
        if nom != routeur:
            continue
        if not any(k.arg == "dependencies" for k in noeud.keywords):
            sans_garde.append(nom)

    assert not sans_garde, f"routeur monte sans authentification : {sans_garde}"
