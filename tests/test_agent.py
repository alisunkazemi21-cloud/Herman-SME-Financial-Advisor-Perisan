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

@pytest.mark.parametrize("result", [[], {"message": None}, {"message": {"content": ""}},
    {"done": False, "message": {"content": "partial"}},
    {"message": {"content": "x", "tool_calls": [{"name": "approve"}]}},
    {"message": {"content": "x" * 12001}}])
def test_invalid_or_action_model_outputs_rejected(monkeypatch, result):
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self, limit):
            return json.dumps(result).encode()
    class Opener:
        def open(self, request, timeout):
            return Response()
    monkeypatch.setattr("urllib.request.build_opener", lambda *args: Opener())
    with pytest.raises(ValueError):
        FinancialAgent().advise({"question_fa": "x"})


def test_oversize_context_never_opens_network(monkeypatch):
    def unexpected(*args):
        pytest.fail("oversize input must fail before network access")
    monkeypatch.setattr("urllib.request.build_opener", unexpected)
    with pytest.raises(ValueError):
        FinancialAgent().advise({"value": "x"*65536})


def test_response_byte_limit(monkeypatch):
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self, limit):
            assert limit == 65537
            return b" " * limit
    class Opener:
        def open(self, request, timeout):
            return Response()
    monkeypatch.setattr("urllib.request.build_opener", lambda *args: Opener())
    with pytest.raises(ValueError):
        FinancialAgent().advise({})


def test_incomplete_http_response_rejected(monkeypatch):
    from http.client import IncompleteRead
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self, limit):
            raise IncompleteRead(b"partial")
    class Opener:
        def open(self, request, timeout):
            return Response()
    monkeypatch.setattr("urllib.request.build_opener", lambda *args: Opener())
    with pytest.raises(ValueError):
        FinancialAgent().advise({})
