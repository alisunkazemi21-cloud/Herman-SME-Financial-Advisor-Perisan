"""Real database checks for reviewed knowledge and read-only context boundaries."""

# ruff: noqa: E402
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

psycopg = pytest.importorskip("psycopg")
pytest.importorskip("fastapi")
from fastapi.testclient import TestClient
from test_backend import backend as backend_fixture
from test_backend import database as database_fixture
from test_backend import inventory_payload as inventory_fixture
from test_backend import seed_inventory

from src.backend.advisor import (
    BusinessAdvisor,
    BusinessContextInput,
    KnowledgeDecision,
    KnowledgeProposal,
    QuickContextInput,
    bounded_context,
    quick_context,
)
from src.backend.api import create_app
from src.backend.database import AccessDenied
from src.backend.portfolio import FIELDS, FinancialPortfolio, FinancialSnapshot, indicators
from src.backend.service import Conflict, NotFound

backend = backend_fixture
database = database_fixture
inventory_payload = inventory_fixture

NOW = datetime(2026, 10, 8, tzinfo=timezone.utc)


def proposal(b, text="ضایعات باید روزانه ثبت شوند", **changes):
    doc = b["service"].document(
        b["owner"], b["business"], "knowledge-doc", "policy.txt", "text/plain", b"policy"
    )
    fields = dict(
        key="waste.policy",
        statement_fa=text,
        evidence=dict(document_id=doc, locator="line:1"),
        valid_from="2026-01-01T00:00:00Z",
    )
    fields.update(changes)
    return KnowledgeProposal(**fields)


def request(**changes):
    fields = dict(question_fa="علت اختلاف چیست؟", effective_at=NOW, knowledge_keys=["waste.policy"])
    fields.update(changes)
    return BusinessContextInput(**fields)


def approve(a, b, identity, key="review", approved=True):
    return a.decide(
        b["owner"],
        b["business"],
        key,
        identity,
        KnowledgeDecision(approved=approved, reason_fa="شاهد بررسی شد"),
    )


def test_review_required_and_interval_boundaries(backend):
    b = backend
    a = BusinessAdvisor(b["service"])
    value = proposal(b, valid_to=NOW)
    identity = a.propose(b["editor"], b["business"], "proposal", value)
    assert a.context(b["viewer"], b["business"], request())["knowledge"][0]["status"] == "missing"
    with pytest.raises(AccessDenied):
        a.decide(
            b["editor"],
            b["business"],
            "bad",
            identity,
            KnowledgeDecision(approved=True, reason_fa="not a reviewer"),
        )
    approve(a, b, identity)
    before = request(effective_at="2026-10-07T00:00:00Z")
    group = a.context(b["viewer"], b["business"], before)["knowledge"][0]
    assert group["status"] == "confirmed"
    assert group["claims"][0]["reviewed_by"] == str(b["owner"])
    assert len(group["claims"][0]["document_sha256"]) == 64
    assert a.context(b["owner"], b["business"], request())["knowledge"][0]["status"] == "missing"
    assert (
        a.context(b["owner"], b["business"], request(effective_at="2025-12-31T00:00:00Z"))["knowledge"][0][
            "status"
        ]
        == "missing"
    )


def test_conflict_and_rejection_are_not_silently_selected(backend):
    b = backend
    a = BusinessAdvisor(b["service"])
    for index, text in enumerate(["روزانه", "هفتگی", "رد شده"]):
        identity = a.propose(b["owner"], b["business"], str(index), proposal(b, text))
        approve(a, b, identity, "review" + str(index), approved=index < 2)
    group = a.context(b["owner"], b["business"], request())["knowledge"][0]
    assert group["status"] == "conflict"
    assert {r["statement_fa"] for r in group["claims"]} == {"روزانه", "هفتگی"}


def test_idempotent_concurrent_proposal_and_immutable_decision(backend):
    b = backend
    a = BusinessAdvisor(b["service"])
    value = proposal(b)
    with ThreadPoolExecutor(max_workers=3) as pool:
        ids = list(pool.map(lambda _: a.propose(b["owner"], b["business"], "same", value), range(3)))
    assert len(set(ids)) == 1
    assert approve(a, b, ids[0]) == approve(a, b, ids[0])
    with pytest.raises(Conflict):
        a.propose(b["owner"], b["business"], "same", proposal(b, "different"))
    with pytest.raises(Conflict):
        approve(a, b, ids[0], "different-decision", False)
    with (
        pytest.raises(psycopg.errors.InsufficientPrivilege),
        b["db"].transaction(b["owner"], b["business"]) as c,
    ):
        c.execute("UPDATE herman.knowledge_claims SET statement_fa='overwrite'")
    with pytest.raises(psycopg.errors.InsufficientPrivilege), psycopg.connect(b["admin"]) as c:
        c.execute("DELETE FROM herman.knowledge_decisions WHERE business_id=%s", (b["business"],))


def test_rls_evidence_and_actor_forgery(backend):
    b = backend
    a = BusinessAdvisor(b["service"])
    identity = a.propose(b["owner"], b["business"], "x", proposal(b))
    with b["db"].transaction(b["stranger"], b["other"]) as c:
        assert c.execute("SELECT * FROM herman.knowledge_claims").fetchall() == []
    with pytest.raises(AccessDenied):
        a.context(b["stranger"], b["business"], request())
    with pytest.raises(NotFound):
        a.claim(b["stranger"], b["other"], identity)
    with pytest.raises(NotFound):
        a.propose(b["stranger"], b["other"], "cross", proposal(b))
    with (
        pytest.raises(psycopg.errors.InsufficientPrivilege),
        b["db"].transaction(b["editor"], b["business"]) as c,
    ):
        c.execute(
            "INSERT INTO herman.knowledge_decisions(business_id,claim_id,approved,created_by,reason_fa) "
            "VALUES(%s,%s,true,%s,'forged')",
            (b["business"], identity, b["owner"]),
        )
    with pytest.raises(AccessDenied):
        a.propose(b["viewer"], b["business"], "viewer", proposal(b))


def test_tampered_knowledge_evidence_fails_closed(backend):
    b = backend
    a = BusinessAdvisor(b["service"])
    value = proposal(b)
    identity = a.propose(b["owner"], b["business"], "x", value)
    approve(a, b, identity)
    metadata, _ = b["service"].read_document(b["owner"], b["business"], value.evidence.document_id)
    (b["blob_root"] / str(b["business"]) / metadata["sha256"]).write_bytes(b"changed")
    with pytest.raises(Conflict):
        a.context(b["owner"], b["business"], request())


def test_business_context_exact_analysis_no_new_writes(backend, inventory_payload):
    b = backend
    a = BusinessAdvisor(b["service"])
    value = seed_inventory(b, inventory_payload)
    identity = b["service"].analyze(b["owner"], b["business"], "analysis", value)
    with b["db"].transaction(b["owner"], b["business"]) as c:
        before = c.execute("SELECT count(*) AS n FROM herman.audit_events").fetchone()["n"]
    ctx = a.context(b["viewer"], b["business"], request(analysis_id=identity))
    assert Decimal(ctx["analysis"]["result"]["unexplained_shortage"]) == Decimal("7000")
    assert ctx["analysis"]["input_sha256"]
    assert not ctx["persisted"]
    assert ctx["explanation_fa"] == ctx["analysis"]["result"]["explanation_fa"]
    with b["db"].transaction(b["owner"], b["business"]) as c:
        assert c.execute("SELECT count(*) AS n FROM herman.audit_events").fetchone()["n"] == before
    with pytest.raises(NotFound):
        a.context(b["stranger"], b["other"], request(analysis_id=identity))


def test_quick_never_uses_service_and_rejects_history_fields(inventory_payload):
    inventory_payload["opening"] = None
    ctx = quick_context(QuickContextInput(question_fa="سوابق را بیاور", inventory=inventory_payload))
    assert ctx["inventory"]["status"] == "incomplete"
    assert ctx["knowledge"] == [] and not ctx["history_used"] and not ctx["persisted"]
    with pytest.raises(ValueError):
        QuickContextInput(question_fa="x", inventory=inventory_payload, analysis_id=uuid4())


def test_context_limits_and_validation(backend):
    with pytest.raises(ValueError):
        request(effective_at="2026-10-08T00:00:00")
    with pytest.raises(ValueError):
        request(knowledge_keys=["waste.policy"] * 2)
    with pytest.raises(ValueError):
        bounded_context(dict(text="x" * 65536))
    b = backend
    a = BusinessAdvisor(b["service"])
    for i in range(21):
        identity = a.propose(b["owner"], b["business"], str(i), proposal(b, str(i)))
        approve(a, b, identity, "review" + str(i))
    with pytest.raises(ValueError):
        a.context(b["owner"], b["business"], request())


def test_api_approval_auth_and_quick_context(backend, inventory_payload):
    b = backend
    with TestClient(create_app(b["db"], b["blob_root"])) as client:
        base = f"/businesses/{b['business']}"
        headers = {"Authorization": "Bearer " + b["tokens"][0], "Idempotency-Key": "api-claim"}
        body = proposal(b).model_dump(mode="json")
        assert client.post(base + "/knowledge", json=body).status_code == 401
        r = client.post(base + "/knowledge", json=body, headers=headers)
        assert r.status_code == 201, r.text
        identity = r.json()["id"]
        r = client.post(
            base + f"/knowledge/{identity}/decision",
            json=dict(approved=True, reason_fa="بررسی شد"),
            headers={**headers, "Idempotency-Key": "api-review"},
        )
        assert r.status_code == 201, r.text
        r = client.post(base + "/advisor/context", json=request().model_dump(mode="json"), headers=headers)
        assert r.status_code == 200 and r.headers["cache-control"] == "no-store", r.text
        assert r.json()["knowledge"][0]["status"] == "confirmed"
        r = client.post(
            "/quick/advisor/context", json=dict(question_fa="x", inventory=inventory_payload), headers=headers
        )
        assert r.status_code == 200 and r.headers["cache-control"] == "no-store", r.text
        assert not r.json()["history_used"]


# Portfolio additions: independent financial expectations and tenant-scoped summaries.


def financial_value(b, **overrides):
    evidence = proposal(b).evidence.model_dump(mode="json")
    values = dict(
        opening_cash="100",
        cash_inflows="250",
        cash_outflows="180",
        revenue="400",
        net_income="80",
        current_assets="600",
        current_liabilities="300",
    )
    values.update(overrides)
    return FinancialSnapshot(
        period_start="2026-09-01",
        period_end="2026-09-30",
        **{k: dict(value=v, evidence=evidence) for k, v in values.items()},
    )


def test_cashflow_and_five_indicators_exact(backend):
    view = indicators(financial_value(backend))
    metrics = {k["key"]: k["value"] for k in view["kpis"]}
    assert metrics == dict(
        revenue="400", net_income="80", net_cash_flow="70", current_ratio="2", net_margin="0.2"
    )
    assert [s["value"] for s in view["cashflow_diagram"]["steps"]] == ["100", "250", "-180", "170"]
    assert view["constants"]["closing_cash"] == "170"
    assert set(view["evidence"]) == set(FIELDS)
    zero = indicators(
        financial_value(
            backend,
            revenue="0",
            current_liabilities="0",
            net_income="-10",
            opening_cash="-100",
            cash_outflows="350",
        )
    )
    assert zero["constants"]["closing_cash"] == "-200"
    assert [m["value"] for m in zero["kpis"][-2:]] == [None, None]
    for invalid in [dict(revenue=0.1), dict(cash_inflows="-1"), dict(net_income="1.0000001")]:
        with pytest.raises(ValueError):
            financial_value(backend, **invalid)


def test_financial_review_conflicts_and_missing(backend):
    b = backend
    a = BusinessAdvisor(b["service"])
    f = FinancialPortfolio(b["service"])
    assert a.overview(b["owner"], b["business"], NOW)["financial"]["status"] == "missing"
    value = financial_value(b)
    identity = f.propose(b["editor"], b["business"], "finance", value)
    assert f.propose(b["editor"], b["business"], "finance", value) == identity
    assert a.overview(b["owner"], b["business"], NOW)["financial"]["status"] == "missing"
    with pytest.raises(AccessDenied):
        f.decide(b["editor"], b["business"], "wrong-role", identity, True, "review")
    f.decide(b["owner"], b["business"], "review-finance", identity, True, "review")
    view = a.overview(b["viewer"], b["business"], NOW)["financial"]
    assert view["status"] == "confirmed" and view["snapshot_id"] == str(identity)
    assert view["constants"]["closing_cash"] == "170"
    assert view["document_hashes"]
    assert (
        a.overview(b["owner"], b["business"], datetime(2026, 9, 1, tzinfo=timezone.utc))["financial"][
            "status"
        ]
        == "missing"
    )
    second = f.propose(b["owner"], b["business"], "competing", financial_value(b, revenue="800"))
    f.decide(b["owner"], b["business"], "review-competing", second, True, "review")
    conflict = a.overview(b["owner"], b["business"], NOW)["financial"]
    assert conflict["status"] == "conflict" and conflict["cashflow_diagram"] is None
    assert all(k["value"] is None for k in conflict["kpis"])


def test_financial_cross_tenant_immutable_and_tampering(backend):
    b = backend
    f = FinancialPortfolio(b["service"])
    value = financial_value(b)
    identity = f.propose(b["owner"], b["business"], "f", value)
    with pytest.raises(NotFound):
        f.propose(b["stranger"], b["other"], "cross", value)
    with b["db"].transaction(b["stranger"], b["other"]) as c:
        assert c.execute("SELECT * FROM herman.financial_snapshots").fetchall() == []
        assert c.execute("SELECT * FROM herman.financial_snapshot_sources").fetchall() == []
    with pytest.raises(psycopg.errors.InsufficientPrivilege), psycopg.connect(b["admin"]) as c:
        c.execute("UPDATE herman.financial_snapshots SET payload='{}' WHERE business_id=%s", (b["business"],))
    metadata, _ = b["service"].read_document(b["owner"], b["business"], value.revenue.evidence.document_id)
    (b["blob_root"] / str(b["business"]) / metadata["sha256"]).write_bytes(b"changed")
    with pytest.raises(Conflict):
        f.decide(b["owner"], b["business"], "review", identity, True, "review")
    assert f.read(b["owner"], b["business"], identity)["decision"] is None


def test_portfolio_membership_pagination_and_conflict_highlight(backend, inventory_payload):
    b = backend
    a = BusinessAdvisor(b["service"])
    second_business = b["service"].create_business(b["owner"], "فروشگاه", "retail", "second")
    pending = a.propose(b["owner"], b["business"], "pending", proposal(b))
    assert a.claim(b["owner"], b["business"], pending)["decision"] is None
    for i, text in enumerate(["روزانه", "هفتگی"]):
        identity = a.propose(b["owner"], b["business"], str(i), proposal(b, text))
        approve(a, b, identity, "review" + str(i))
    value = seed_inventory(b, inventory_payload)
    b["service"].analyze(b["owner"], b["business"], "analysis", value)
    first = a.portfolio(b["owner"], NOW, limit=1)
    second = a.portfolio(b["owner"], NOW, after=first["next_cursor"], limit=1)
    assert second["next_cursor"] is None
    assert {page["businesses"][0]["profile"]["id"] for page in [first, second]} == {
        str(b["business"]),
        str(second_business),
    }
    view = a.overview(b["viewer"], b["business"], NOW)
    assert isinstance(view["recent_inventory_analyses"][0]["needs_review"], bool)
    assert view["pending_knowledge_reviews"] == 1
    assert view["conflicting_knowledge_keys"] == 1
    assert view["knowledge_highlights"][0]["status"] == "conflict"
    assert view["knowledge_highlights"][0]["preview_fa"] is None
    assert Decimal(view["recent_inventory_analyses"][0]["unexplained_shortage"]) == Decimal("7000")
    with pytest.raises(AccessDenied):
        a.overview(b["stranger"], b["business"], NOW)


def test_financial_and_portfolio_api(backend):
    b = backend
    with TestClient(create_app(b["db"], b["blob_root"])) as client:
        base = f"/businesses/{b['business']}"
        headers = {"Authorization": "Bearer " + b["tokens"][0], "Idempotency-Key": "financial-api"}
        r = client.post(
            base + "/financial-snapshots", json=financial_value(b).model_dump(mode="json"), headers=headers
        )
        assert r.status_code == 201, r.text
        identity = r.json()["id"]
        r = client.post(
            base + f"/financial-snapshots/{identity}/decision",
            json=dict(approved=True, reason_fa="بررسی شد"),
            headers={**headers, "Idempotency-Key": "financial-review"},
        )
        assert r.status_code == 201, r.text
        r = client.get("/advisor/portfolio", params=dict(effective_at=NOW.isoformat()), headers=headers)
        assert r.status_code == 200, r.text
        assert r.headers["cache-control"] == "no-store"
        assert r.json()["businesses"][0]["financial"]["cashflow_diagram"]["type"] == "waterfall"
        assert client.get("/advisor/portfolio", params=dict(effective_at=NOW.isoformat())).status_code == 401
