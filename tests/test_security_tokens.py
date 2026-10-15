"""JWT helpers in th2etl.helpers.security: what callers rely on.

Pinned while moving off python-jose (CVE-2026-85394, critical, no fix; it also
pulls ecdsa, CVE-2024-23342) to PyJWT. Every rejection must surface as a 401
HTTPException -- not a library exception and not a NameError.
"""

from datetime import timedelta

import pytest
from fastapi import HTTPException

from th2etl.helpers import security


@pytest.fixture(autouse=True)
def signing_key(monkeypatch):
    monkeypatch.setattr(security.settings, "encrypt_key", "k" * 32)
    monkeypatch.setattr(security.settings, "jwt_algorithm", "HS256")


def test_access_token_round_trip_keeps_claims():
    token = security.create_access_token({"sub": "alice", "agent_id": "42"})
    assert isinstance(token, str)
    payload = security.decode_access_token(token)
    assert payload["sub"] == "alice"
    assert payload["agent_id"] == "42"
    assert payload["type"] == "access"


def test_refresh_token_is_not_accepted_as_access_token():
    token = security.create_refresh_token({"sub": "alice"})
    assert security.decode_refresh_token(token)["type"] == "refresh"
    with pytest.raises(HTTPException) as e:
        security.decode_access_token(token)
    assert e.value.status_code == 401


def test_tampered_token_is_rejected_with_401():
    token = security.create_access_token({"sub": "alice"})
    with pytest.raises(HTTPException) as e:
        security.decode_access_token(token[:-2] + ("AA" if token[-2:] != "AA" else "BB"))
    assert e.value.status_code == 401


def test_token_signed_with_another_key_is_rejected(monkeypatch):
    token = security.create_access_token({"sub": "alice"})
    monkeypatch.setattr(security.settings, "encrypt_key", "z" * 32)
    with pytest.raises(HTTPException) as e:
        security.decode_access_token(token)
    assert e.value.status_code == 401


def test_expired_agent_refresh_token_says_expired():
    token = security.create_agent_refresh_token({"sub": "alice"}, expires_days=-1)
    with pytest.raises(HTTPException) as e:
        security.decode_agent_refresh_token(token)
    assert e.value.status_code == 401
    assert "expired" in e.value.detail


def test_agent_refresh_mints_a_fresh_access_token():
    refresh = security.create_agent_refresh_token({"sub": "alice", "agent_id": "9"})
    access = security.refresh_access_token_from_agent_refresh(refresh)
    payload = security.decode_access_token(access)
    assert payload["sub"] == "alice"
    assert payload["agent_id"] == "9"


def test_custom_expiry_is_honoured():
    token = security.create_access_token({"sub": "alice"}, expires_delta=timedelta(seconds=-5))
    with pytest.raises(HTTPException) as e:
        security.decode_access_token(token)
    assert e.value.status_code == 401
