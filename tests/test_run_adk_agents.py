"""RunAdkAgentsBloc resolves agent_id/user_id/message_text from run variables
(run_context.context_vars), falling back to static config. HTTP + JWT mocked."""
from __future__ import annotations

import pytest

import th2etl.blocs.transformers as tr
from th2etl.blocs.transformers import RunAdkAgentsBloc
from th2etl.pipelines.context import RunContext


class _Resp:
    status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return {"ok": True}


@pytest.fixture
def captured(monkeypatch) -> dict:
    cap: dict = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        cap.update(url=url, headers=headers, payload=json, timeout=timeout)
        return _Resp()

    monkeypatch.setattr(tr.requests, "post", fake_post)
    monkeypatch.setattr(tr, "create_access_token", lambda data: f"tok-{data.get('sub')}")
    return cap


CFG = {
    "base_url": "https://api-agent-dev.thaink2.fr",
    "agent_id": "cfg_agent",
    "user_id": "cfg_user",
    "message_text": "cfg_msg",
}


def test_run_variables_override_config(captured):
    bloc = RunAdkAgentsBloc("a", CFG)
    ctx = RunContext(context_vars={"agent_id": "run_agent", "user_id": "run@x.com", "message_text": "hello"})
    bloc.execute(ctx)
    p = captured["payload"]
    assert p["agent_name"] == "run_agent"
    assert p["user_id"] == "run@x.com"
    assert p["new_message"]["parts"][0]["text"] == "hello"
    assert captured["url"] == "https://api-agent-dev.thaink2.fr/api/adk/run"
    assert ctx.context_vars["a_result"] == {"ok": True}


def test_config_fallback_when_no_variables(captured):
    RunAdkAgentsBloc("a", CFG).execute(RunContext())
    p = captured["payload"]
    assert p["agent_name"] == "cfg_agent"
    assert p["user_id"] == "cfg_user"
    assert p["new_message"]["parts"][0]["text"] == "cfg_msg"


def test_missing_required_value_raises(captured):
    # base_url only — agent_id/user_id/message_text neither in config nor variables
    bloc = RunAdkAgentsBloc("a", {"base_url": "https://x"})
    with pytest.raises(ValueError) as e:
        bloc.execute(RunContext())
    assert "agent_id" in str(e.value)


def test_base_url_only_config_is_valid():
    """The seed creates these blocs with base_url only; construction must not raise."""
    from th2etl.blocs.schemas import RunAdkAgentsConfig

    cfg = RunAdkAgentsConfig(base_url="https://x")
    assert cfg.agent_id is None and cfg.user_id is None and cfg.message_text is None
