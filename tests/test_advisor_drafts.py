"""Draft endpoints use authoritative context and cannot post or approve records."""

# ruff: noqa: E402
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

pytest.importorskip("psycopg")
pytest.importorskip("fastapi")
from fastapi.testclient import TestClient
from test_backend import backend as backend_fixture
from test_backend import database as database_fixture
from test_backend import inventory_payload as inventory_fixture
from test_backend import seed_inventory

from src.backend.api import create_app

backend = backend_fixture
database = database_fixture
inventory_payload = inventory_fixture


class DraftStub:
    def __init__(self):
        self.contexts = []

    def advise(self, context):
        self.contexts.append(context)
        return dict(text_fa="شواهد اختلاف را بررسی کنید", status_fa="پیش‌نویس", model="test-only")


def headers(b):
    return {"Authorization": "Bearer " + b["tokens"][0]}


def test_business_draft_receipt_and_access_before_model(backend, inventory_payload):
    b = backend
    value = seed_inventory(b, inventory_payload)
    identity = b["service"].analyze(b["owner"], b["business"], "analysis", value)
    agent = DraftStub()
    body = dict(
        question_fa="اختلاف را توضیح بده", effective_at="2026-10-08T00:00:00Z", analysis_id=str(identity)
    )
    with TestClient(create_app(b["db"], b["blob_root"], draft_agent=agent)) as client:
        path = f"/businesses/{b['business']}/advisor/draft"
        assert client.post(path, json=body).status_code == 401
        forbidden = client.post(f"/businesses/{b['other']}/advisor/draft", json=body, headers=headers(b))
        assert forbidden.status_code == 403 and not agent.contexts
        result = client.post(path, json=body, headers=headers(b))
        assert result.status_code == 200, result.text
        data = result.json()
        assert data["status"] == "draft" and not data["verified"] and not data["persisted"]
        assert data["context"] == agent.contexts[0]
        assert data["context"]["analysis"]["id"] == str(identity)
        digest = hashlib.sha256(
            json.dumps(data["context"], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        assert data["context_sha256"] == digest
        assert result.headers["cache-control"] == "no-store"
    with b["db"].transaction(b["owner"], b["business"]) as c:
        assert c.execute("SELECT count(*) AS n FROM herman.analysis_runs").fetchone()["n"] == 1


def test_quick_draft_no_business_reads(backend, inventory_payload, monkeypatch):
    b = backend
    agent = DraftStub()

    def forbidden(*args, **kwargs):
        pytest.fail("Quick draft must not open a scoped transaction")

    monkeypatch.setattr(b["db"], "transaction", forbidden)
    inventory_payload["opening"] = None
    with TestClient(create_app(b["db"], b["blob_root"], draft_agent=agent)) as client:
        result = client.post(
            "/quick/advisor/draft",
            headers=headers(b),
            json=dict(question_fa="از سابقه استفاده کن", inventory=inventory_payload),
        )
        assert result.status_code == 200, result.text
        assert result.json()["context"]["inventory"]["status"] == "incomplete"
        assert not agent.contexts[0]["history_used"]


def test_disabled_and_failed_inference_are_generic(backend, inventory_payload):
    b = backend
    body = dict(question_fa="x", inventory=inventory_payload)
    with TestClient(create_app(b["db"], b["blob_root"])) as client:
        result = client.post("/quick/advisor/draft", json=body, headers=headers(b))
        assert result.status_code == 503 and result.headers["cache-control"] == "no-store"

    class Failing:
        def advise(self, context):
            raise OSError("private transport details")

    with TestClient(create_app(b["db"], b["blob_root"], draft_agent=Failing())) as client:
        for _ in range(2):
            result = client.post("/quick/advisor/draft", json=body, headers=headers(b))
            assert result.status_code == 503 and "private" not in result.text
            assert "Retry-After" not in result.headers  # slot was released after failure


def test_inference_capacity_and_slot_release(backend, inventory_payload):
    b = backend
    started = Event()
    release = Event()

    class Slow:
        def advise(self, context):
            started.set()
            assert release.wait(15)
            return dict(text_fa="پیش‌نویس", model="test-only")

    with TestClient(create_app(b["db"], b["blob_root"], draft_agent=Slow())) as client:

        def call():
            return client.post(
                "/quick/advisor/draft",
                json=dict(question_fa="x", inventory=inventory_payload),
                headers=headers(b),
            )

        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(call)
            try:
                assert started.wait(10)
                busy = call()
                assert busy.status_code == 503 and busy.headers["retry-after"] == "5"
            finally:
                release.set()
            assert pending.result(timeout=10).status_code == 200
        assert call().status_code == 200


def test_draft_can_include_only_reviewed_financial_snapshot(backend):
    from test_advisor_context import financial_value

    from src.backend.portfolio import FinancialPortfolio

    b = backend
    finance = FinancialPortfolio(b["service"])
    identity = finance.propose(b["owner"], b["business"], "financial", financial_value(b))
    agent = DraftStub()
    body = dict(
        question_fa="جریان نقد را توضیح بده", effective_at="2026-10-08T00:00:00Z", include_financial=True
    )
    with TestClient(create_app(b["db"], b["blob_root"], draft_agent=agent)) as client:
        route = f"/businesses/{b['business']}/advisor/draft"
        result = client.post(route, json=body, headers=headers(b))
        assert result.status_code == 200, result.text
        assert agent.contexts[-1]["financial"]["status"] == "missing"
        finance.decide(b["owner"], b["business"], "review", identity, True, "بررسی شد")
        result = client.post(route, json=body, headers=headers(b))
        assert result.status_code == 200, result.text
        context = agent.contexts[-1]["financial"]
        assert context["snapshot_id"] == str(identity)
        assert context["constants"]["closing_cash"] == "170"
        assert len(context["kpis"]) == 5 and context["document_hashes"]
