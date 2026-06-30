"""RunAdkFromJwtBloc forwards the per-run jwt_token to /api/adk/run_from_jwt
as a Bearer header (faithful to the MageAI flow). HTTP mocked."""
from __future__ import annotations

import pytest

import th2etl.blocs.transformers as tr
from th2etl.blocs.transformers import RunAdkFromJwtBloc
from th2etl.pipelines.context import RunContext


class _Resp:
    def raise_for_status(self):
        return None

    def json(self):
        return {"ok": True, "token_rotated": True}


@pytest.fixture
def captured(monkeypatch) -> dict:
    cap: dict = {}

    def fake_post(url, headers=None, json=None):
        cap.update(url=url, headers=headers, payload=json)
        return _Resp()

    monkeypatch.setattr(tr.requests, "post", fake_post)
    return cap


def test_jwt_from_run_variables_sent_as_bearer(captured):
    bloc = RunAdkFromJwtBloc("a", {"base_url": "https://api-agent-dev.thaink2.fr"})
    ctx = RunContext(context_vars={"jwt_token": "TOK", "agent_id": "42", "agent_meta": {"x": 1}})
    bloc.execute(ctx)
    assert captured["url"] == "https://api-agent-dev.thaink2.fr/api/adk/run_from_jwt"
    assert captured["headers"]["Authorization"] == "Bearer TOK"
    assert captured["payload"] == {"agent_id": "42", "data": {"x": 1}}
    assert ctx.context_vars["a_result"]["ok"] is True


def test_config_fallback_for_jwt(captured):
    bloc = RunAdkFromJwtBloc("a", {"base_url": "https://x", "jwt_token": "CFG", "agent_id": "9"})
    bloc.execute(RunContext())
    assert captured["headers"]["Authorization"] == "Bearer CFG"
    assert captured["payload"]["agent_id"] == "9"


def test_missing_jwt_raises(captured):
    with pytest.raises(ValueError) as e:
        RunAdkFromJwtBloc("a", {"base_url": "https://x"}).execute(RunContext())
    assert "jwt_token" in str(e.value)


def test_registered_as_factory():
    from th2etl.pipelines.pipeline import build_bloc_from_record

    bloc = build_bloc_from_record("j", "run_adk_from_jwt", {"base_url": "https://x"})
    assert isinstance(bloc, RunAdkFromJwtBloc)
