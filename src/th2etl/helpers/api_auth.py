"""Authentification des appels entrants sur l'API th2etl.

Le reglage ``api_key`` existait deja et etait renseigne en production, mais
aucune ligne ne le lisait : l'API d'orchestration repondait a tout le monde.
Ce module le branche.

La cle protege les routes metier. ``/`` et ``/health`` restent ouvertes : une
sonde de disponibilite ne doit pas avoir besoin d'un secret.
"""
from __future__ import annotations

import logging
import secrets

from fastapi import Header, HTTPException, status

from th2etl.configs.settings import get_settings

logger = logging.getLogger(__name__)

PREFIXE = "Bearer "


def exiger_cle_api(authorization: str | None = Header(default=None)) -> None:
    """Refuse la requete si l'en-tete ne porte pas la cle attendue."""
    attendue = (get_settings().api_key or "").strip()

    # Une chaine vide satisfait la validation pydantic (`api_key: str` accepte
    # ""), et laisserait donc l'API ouverte a tout le monde sans qu'aucune
    # erreur ne le signale. On refuse, et on le dit dans les journaux.
    if not attendue:
        logger.error(
            "[AUTH] API_KEY vide : toutes les routes metier sont refusees. "
            "Renseigner API_KEY pour rouvrir le service."
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentification non configuree : renseigner API_KEY.",
        )

    if not authorization or not authorization.startswith(PREFIXE):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Cle d'API manquante.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    fournie = authorization[len(PREFIXE):].strip()

    # Comparaison a temps constant : `==` s'arrete au premier caractere qui
    # differe et laisse deviner la cle, mesure apres mesure.
    if not secrets.compare_digest(fournie, attendue):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Cle d'API invalide.",
            headers={"WWW-Authenticate": "Bearer"},
        )
