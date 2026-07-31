import os

# Provide the minimal required settings BEFORE any th2etl import triggers
# get_settings() at module import time. No real database connection happens
# in these unit tests.
os.environ.setdefault("DATABASE_NAME", "testdb")
os.environ.setdefault("DATABASE_USER", "testuser")
os.environ.setdefault("DATABASE_PASSWORD", "testpass")
os.environ.setdefault("API_KEY", "test-api-key")

# Les routes metier exigent desormais la cle d'API. Les tests qui les appellent
# la presentent via cet en-tete ; ceux qui verifient le refus s'en passent
# volontairement.
EN_TETE_AUTH = {"Authorization": f"Bearer {os.environ['API_KEY']}"}
