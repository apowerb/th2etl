import os

# Provide the minimal required settings BEFORE any th2etl import triggers
# get_settings() at module import time. No real database connection happens
# in these unit tests.
os.environ.setdefault("DATABASE_NAME", "testdb")
os.environ.setdefault("DATABASE_USER", "testuser")
os.environ.setdefault("DATABASE_PASSWORD", "testpass")
os.environ.setdefault("API_KEY", "test-api-key")

# Business routes now require the API key. Tests that call them present
# it via this header; tests that verify the refusal deliberately omit
# it.
AUTH_HEADER = {"Authorization": f"Bearer {os.environ['API_KEY']}"}
