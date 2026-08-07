"""RunAdkFromJwtBloc forwards the per-run jwt_token to /api/adk/run_from_jwt
as a Bearer header (faithful to the MageAI flow). HTTP mocked."""
from __future__ import annotations

import pytest

import th2etl.blocs.transformers as tr
from th2etl.blocs.transformers import RunAdkFromJwtBloc
from th2etl.pipelines.context import RunContext


class _Resp:
    status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return {"ok": True, "token_rotated": True}


@pytest.fixture
def captured(monkeypatch) -> dict:
    cap: dict = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        cap.update(url=url, headers=headers, payload=json, timeout=timeout)
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


def test_http_call_uses_timeout_and_logs_event(captured, caplog):
    """Blind spot #4: without a timeout, a hung th2agent leaves the run
    'running' forever. The bloc must pass http_timeout AND log bloc.http_call."""
    bloc = RunAdkFromJwtBloc("a", {"base_url": "https://x", "http_timeout": 7.5})
    with caplog.at_level("INFO", logger="th2etl.blocs.transformers"):
        bloc.execute(RunContext(context_vars={"jwt_token": "TOK"}))
    assert captured["timeout"] == 7.5
    evt = [r for r in caplog.records if getattr(r, "event", None) == "bloc.http_call"]
    assert evt and evt[-1].http_status == 200 and evt[-1].bloc == "a"


def test_post_helper_logs_error_level_on_http_error_status(monkeypatch, caplog):
    """A 4xx/5xx returned normally by requests (no exception) must still be an
    ERROR-level bloc.http_call, else it's invisible when filtering by level."""
    class _R:
        status_code = 503

    monkeypatch.setattr(tr.requests, "post", lambda url, timeout=None, **k: _R())
    with caplog.at_level("INFO", logger="th2etl.blocs.transformers"):
        tr._post("b", "https://x", timeout=5)
    evt = [r for r in caplog.records if getattr(r, "event", None) == "bloc.http_call"][-1]
    assert evt.levelname == "ERROR"
    assert evt.http_status == 503


def test_config_fallback_for_jwt(captured):
    bloc = RunAdkFromJwtBloc("a", {"base_url": "https://x", "jwt_token": "CFG", "agent_id": "9"})
    bloc.execute(RunContext())
    assert captured["headers"]["Authorization"] == "Bearer CFG"
    assert captured["payload"]["agent_id"] == "9"


def test_missing_jwt_raises(captured):
    with pytest.raises(ValueError) as e:
        RunAdkFromJwtBloc("a", {"base_url": "https://x"}).execute(RunContext())
    assert "jwt_token" in str(e.value)


def test_http_error_propagates_without_setting_result(monkeypatch):
    class _ErrResp:
        response = None
        status_code = 500

        def raise_for_status(self):
            raise tr.requests.exceptions.RequestException("boom")

        def json(self):
            return {}

    monkeypatch.setattr(tr.requests, "post", lambda url, headers=None, json=None, timeout=None: _ErrResp())
    ctx = RunContext(context_vars={"jwt_token": "TOK"})
    with pytest.raises(tr.requests.exceptions.RequestException):
        RunAdkFromJwtBloc("a", {"base_url": "https://x"}).execute(ctx)
    assert "a_result" not in ctx.context_vars


def test_empty_agent_meta_is_honoured(captured):
    bloc = RunAdkFromJwtBloc("a", {"base_url": "https://x"})
    bloc.execute(RunContext(context_vars={"jwt_token": "T", "agent_meta": {}}))
    assert captured["payload"]["data"] == {}


def test_registered_as_factory():
    from th2etl.pipelines.pipeline import build_bloc_from_record

    bloc = build_bloc_from_record("j", "run_adk_from_jwt", {"base_url": "https://x"})
    assert isinstance(bloc, RunAdkFromJwtBloc)
