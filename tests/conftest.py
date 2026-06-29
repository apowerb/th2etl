import os

# Provide the minimal required settings BEFORE any th2etl import triggers
# get_settings() at module import time. No real database connection happens
# until the FastAPI lifespan starts, which these unit tests never enter.
os.environ.setdefault("DATABASE_NAME", "testdb")
os.environ.setdefault("DATABASE_USER", "testuser")
os.environ.setdefault("DATABASE_PASSWORD", "testpass")
os.environ.setdefault("API_KEY", "test-api-key")
