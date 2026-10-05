import json

import pytest

from src.ai_agent.agent import AgentConfig, FinancialAgent


@pytest.mark.parametrize("url", ["https://example.com", "http://evil.test", "http://localhost.evil", 
    "http://127.0.0.1@evil.test", "http://127.0.0.1/path", "http://127.0.0.1?x=1"])
def test_remote_endpoints_rejected(url):
    with pytest.raises(ValueError):
        AgentConfig(base_url=url)


def test_ollama_transport_is_draft_only(monkeypatch):
    captured = {}
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self, limit):
            return json.dumps({"message": {"content": "مطالبات را بررسی کنید"}}).encode()
    class Opener:
        def open(self, request, timeout):
            captured.update(json.loads(request.data))
            return Response()
    monkeypatch.setattr("urllib.request.build_opener", lambda *args: Opener())
    result = FinancialAgent().advise({"current_ratio": "2"})
    assert "پیش‌نویس" in result["status_fa"]
    assert captured["stream"] is False and "tools" not in captured


def test_missing_cashflow_is_explicit_before_advice(demo):
    from src.ai_agent.tools import calculated_context
    result = calculated_context(demo.statement)
    assert result["forecast"]["predictions"] == []
    assert result["forecast"]["diagnostics"]["is_stationary"] is None
    assert "داده" in result["forecast"]["warning_fa"]
