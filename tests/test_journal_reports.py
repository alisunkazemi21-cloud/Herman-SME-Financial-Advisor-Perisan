"""Journal-derived management reports, source receipts and advisor review boundaries."""

# ruff: noqa: E402
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

psycopg = pytest.importorskip("psycopg")
pytest.importorskip("fastapi")
from fastapi.testclient import TestClient
from test_backend import backend as backend_fixture
from test_backend import database as database_fixture

from src.backend import journal_reports
from src.backend.advisor import BusinessAdvisor, BusinessContextInput
from src.backend.api import create_app
from src.backend.database import AccessDenied
from src.backend.journal_reports import (
    JournalReports,
    MappingInput,
    ReportInput,
    ReportReview,
    ReviewInput,
    digest,
)
from src.backend.journals import AccountInput, JournalDecision, JournalInput, Journals
from src.backend.portfolio import FinancialPortfolio, FinancialSnapshot
from src.backend.service import Conflict, NotFound, insert
from src.ingestion.normalizer import to_jalali

backend = backend_fixture
database = database_fixture
START, END = date(2026, 10, 1), date(2026, 10, 9)
NOW = datetime(2026, 10, 10, tzinfo=timezone.utc)


def review():
    return ReviewInput(approved=True, reviewed_values=True, reason_fa="مقادیر و شواهد بررسی شد")


def report_review():
    return ReportReview(**review().model_dump(), scope_confirmed=True)


def seed(b):
    ledger, reports = Journals(b["service"]), JournalReports(b["service"])
    types = {
        "1000": "asset",
        "1001": "asset",
        "1100": "asset",
        "1200": "asset",
        "2000": "liability",
        "3000": "equity",
        "4000": "revenue",
        "5000": "expense",
    }
    for code, kind in types.items():
        ledger.account(
            b["owner"], b["business"], code, AccountInput(code=code, name_fa="حساب نمونه", kind=kind)
        )
    doc = b["service"].document(
        b["owner"], b["business"], "doc", "source.txt", "text/plain", b"synthetic journal source"
    )
    policy = MappingInput(
        title_fa="نگاشت آزمایشی",
        accounts={
            "1000": "cash",
            "1001": "cash",
            "1100": "current_asset",
            "1200": "current_asset",
            "2000": "current_liability",
            "3000": "equity",
            "4000": "revenue",
            "5000": "expense",
        },
        evidence=dict(document_id=doc, locator="ردیف نگاشت"),
    )
    return ledger, reports, doc, policy


def post(b, ledger, doc, key, debit="1000", credit="4000", amount="100", day=END, approve=True):
    value = JournalInput(
        entry_date=day,
        jalali_date=to_jalali(day),
        description_fa="ثبت نمونه",
        lines=[
            dict(
                account_code=debit, side="debit", amount=amount, evidence=dict(document_id=doc, locator=key)
            ),
            dict(
                account_code=credit, side="credit", amount=amount, evidence=dict(document_id=doc, locator=key)
            ),
        ],
    )
    identity = ledger.propose(b["editor"], b["business"], key, value)
    if approve:
        ledger.decide(
            b["owner"], b["business"], key + "-approved", identity, JournalDecision(**review().model_dump())
        )
    return identity


def setup_report(b):
    ledger, reports, doc, policy = seed(b)
    mapping = reports.mapping(b["editor"], b["business"], "mapping", policy)
    reports.review_mapping(b["owner"], b["business"], "mapping-review", mapping, review())
    post(b, ledger, doc, "opening", credit="3000", amount="1000", day=date(2026, 9, 30))
    value = ReportInput(mapping_id=mapping, period_start=START, period_end=END)
    return ledger, reports, doc, value


def test_report_calculates_cash_accruals_and_internal_transfers(backend):
    b = backend
    ledger, reports, doc, value = setup_report(b)
    post(b, ledger, doc, "cash-sale", amount="200")
    post(b, ledger, doc, "credit-sale", debit="1100", amount="100")
    post(b, ledger, doc, "expense", debit="5000", credit="1000", amount="50")
    post(b, ledger, doc, "loan", credit="2000", amount="300")
    post(b, ledger, doc, "transfer", debit="1001", credit="1000", amount="100")
    post(b, ledger, doc, "inventory", debit="1200", credit="2000", amount="200")
    post(b, ledger, doc, "pending", amount="777", approve=False)
    identity = reports.create(b["editor"], b["business"], "report", value)
    row = reports.read(b["viewer"], b["business"], identity)
    result = row["result"]["financial"]
    assert {k: Decimal(v) for k, v in result["constants"].items()} == dict(
        opening_cash=1000,
        cash_inflows=500,
        cash_outflows=50,
        revenue=300,
        net_income=250,
        current_assets=1750,
        current_liabilities=500,
        closing_cash=1450,
    )
    assert result["kpis"][3]["value"] == "3.5"
    assert [Decimal(step["value"]) for step in result["cashflow_diagram"]["steps"]] == [1000, 500, -50, 1450]
    assert result["cashflow_diagram"]["basis"] == "net_cash_per_journal"
    assert row["result"]["source_entries"] == 7 and row["result"]["source_lines"] == 14
    assert row["input_sha256"] == digest(row["manifest"]) and row["result_sha256"] == digest(row["result"])
    assert all("document_id" in line and "locator" in line for line in row["manifest"]["lines"])
    assert not row["freshness"]["stale"] and row["approved"] is None


def test_mapping_requires_complete_typed_accounts_review_and_evidence(backend):
    b = backend
    ledger, reports, doc, policy = seed(b)
    invalid = policy.model_dump()
    invalid["accounts"].pop("4000")
    with pytest.raises(Conflict):
        reports.mapping(b["owner"], b["business"], "missing", MappingInput(**invalid))
    invalid = policy.model_dump()
    invalid["accounts"]["4000"] = "cash"
    with pytest.raises(ValueError):
        reports.mapping(b["owner"], b["business"], "kind", MappingInput(**invalid))
    mapping = reports.mapping(b["editor"], b["business"], "map", policy)
    request = ReportInput(mapping_id=mapping, period_start=START, period_end=END)
    with pytest.raises(Conflict):
        reports.create(b["owner"], b["business"], "pending-map", request)
    with pytest.raises(AccessDenied):
        reports.review_mapping(b["editor"], b["business"], "editor", mapping, review())
    reports.review_mapping(b["owner"], b["business"], "review", mapping, review())
    with pytest.raises(Conflict):
        reports.create(b["owner"], b["business"], "empty-ledger", request)
    post(b, ledger, doc, "sale")
    ledger.account(
        b["owner"], b["business"], "new", AccountInput(code="new", name_fa="حساب جدید", kind="asset")
    )
    with pytest.raises(Conflict):
        reports.create(b["owner"], b["business"], "incomplete-map", request)


def test_reviewed_report_feeds_portfolio_and_explicit_advisor_context(backend):
    b = backend
    _, reports, _, value = setup_report(b)
    identity = reports.create(b["editor"], b["business"], "report", value)
    advisor = BusinessAdvisor(b["service"])
    context = BusinessContextInput(
        question_fa="وضعیت نقد چطور است؟",
        effective_at=NOW,
        journal_report_id=identity,
        include_financial=True,
    )
    assert advisor.overview(b["viewer"], b["business"], NOW)["financial"]["status"] == "missing"
    with pytest.raises(Conflict):
        advisor.context(b["owner"], b["business"], context)
    with pytest.raises(ValueError):
        ReportReview(**review().model_dump())
    with pytest.raises(AccessDenied):
        reports.review(b["editor"], b["business"], "unauthorized", identity, report_review())
    reports.review(b["owner"], b["business"], "approved", identity, report_review())
    result = advisor.context(b["viewer"], b["business"], context)
    assert result["journal"]["report_id"] == str(identity)
    assert result["journal"]["status"] == result["financial"]["status"] == "confirmed"
    assert result["financial"]["source_kind"] == "journal_report"
    assert result["journal"]["constants"]["closing_cash"] == "1000"
    assert "manifest" not in result["journal"] and "trial_balance" not in result["journal"]
    with pytest.raises(ValueError):
        advisor.context(
            b["owner"],
            b["business"],
            context.model_copy(update={"effective_at": datetime(2026, 10, 1, tzinfo=timezone.utc)}),
        )


def test_report_retries_preserve_receipt_and_backdated_posting_marks_stale(backend):
    b = backend
    ledger, reports, doc, value = setup_report(b)
    identity = reports.create(b["editor"], b["business"], "report", value)
    pending = reports.create(b["editor"], b["business"], "second-report", value)
    reports.review(b["owner"], b["business"], "approve", identity, report_review())
    saved = reports.read(b["viewer"], b["business"], identity)
    post(b, ledger, doc, "future", amount="17", day=date(2026, 10, 11))
    assert not reports.read(b["viewer"], b["business"], identity)["freshness"]["stale"]
    post(b, ledger, doc, "backdated", amount="18", day=START)
    changed = reports.read(b["viewer"], b["business"], identity)
    assert changed["freshness"]["stale"]
    assert changed["manifest"] == saved["manifest"] and changed["result"] == saved["result"]
    assert reports.create(b["editor"], b["business"], "report", value) == identity
    with pytest.raises(Conflict):
        reports.review(b["owner"], b["business"], "stale", pending, report_review())
    view = BusinessAdvisor(b["service"]).overview(b["viewer"], b["business"], NOW)["financial"]
    assert view["status"] == "stale" and view["constants"] == {} and view["cashflow_diagram"] is None


def test_statement_and_journal_same_end_date_are_a_conflict(backend):
    b = backend
    _, reports, doc, value = setup_report(b)
    identity = reports.create(b["owner"], b["business"], "report", value)
    reports.review(b["owner"], b["business"], "review", identity, report_review())
    facts = {
        name: dict(value="100", evidence=dict(document_id=doc, locator="1"))
        for name in (
            "opening_cash",
            "cash_inflows",
            "cash_outflows",
            "revenue",
            "net_income",
            "current_assets",
            "current_liabilities",
        )
    }
    financial = FinancialPortfolio(b["service"])
    other = financial.propose(
        b["owner"], b["business"], "statement", FinancialSnapshot(period_start=START, period_end=END, **facts)
    )
    financial.decide(b["owner"], b["business"], "statement-approved", other, True, "بررسی شد")
    result = BusinessAdvisor(b["service"]).overview(b["viewer"], b["business"], NOW)["financial"]
    assert result["status"] == "conflict" and result["constants"] == {}
    assert {r["source_kind"] for r in result["candidate_sources"]} == {"statement", "journal_report"}


def test_reviewed_replacement_restores_fresh_portfolio_and_prevents_two_branches(backend):
    b = backend
    ledger, reports, doc, value = setup_report(b)
    original = reports.create(b["owner"], b["business"], "old", value)
    with pytest.raises(Conflict):
        reports.create(
            b["owner"],
            b["business"],
            "pending-replacement",
            value.model_copy(update={"supersedes": original}),
        )
    reports.review(b["owner"], b["business"], "review-old", original, report_review())
    saved = reports.read(b["owner"], b["business"], original)
    post(b, ledger, doc, "backdated", amount="50", day=START)
    request = value.model_copy(update={"supersedes": original})
    with pytest.raises(Conflict):
        reports.create(
            b["owner"], b["business"], "wrong-period", request.model_copy(update={"period_start": END})
        )
    candidates = [reports.create(b["owner"], b["business"], f"replacement-{n}", request) for n in range(2)]

    def approve(identity):
        try:
            return reports.review(b["owner"], b["business"], str(identity), identity, report_review())
        except psycopg.IntegrityError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(approve, candidates))
    assert sum(item is not None for item in results) == 1
    winner = next(item for item in results if item is not None)
    advisor = BusinessAdvisor(b["service"])
    result = advisor.overview(b["viewer"], b["business"], NOW)["financial"]
    assert result["status"] == "confirmed" and result["report_id"] == str(winner)
    assert result["constants"]["closing_cash"] == "1050"
    old = reports.read(b["viewer"], b["business"], original)
    assert (
        old["superseded_by"] == winner
        and old["manifest"] == saved["manifest"]
        and old["result"] == saved["result"]
    )
    context = advisor.context(
        b["viewer"],
        b["business"],
        BusinessContextInput(question_fa="گزارش قبلی", effective_at=NOW, journal_report_id=original),
    )
    assert context["journal"]["status"] == "superseded" and context["journal"]["constants"] == {}


def test_evidence_tampering_blocks_report_publication_and_context(backend):
    b = backend
    _, reports, doc, value = setup_report(b)
    identity = reports.create(b["owner"], b["business"], "report", value)
    approved = reports.create(b["owner"], b["business"], "approved-report", value)
    reports.review(b["owner"], b["business"], "approved", approved, report_review())
    metadata, _ = b["service"].read_document(b["owner"], b["business"], doc)
    (b["blob_root"] / str(b["business"]) / metadata["sha256"]).write_bytes(b"changed")
    with pytest.raises(Conflict):
        reports.review(b["owner"], b["business"], "review", identity, report_review())
    with pytest.raises(Conflict):
        reports.read(b["viewer"], b["business"], identity)
    with pytest.raises(Conflict):
        BusinessAdvisor(b["service"]).context(
            b["viewer"],
            b["business"],
            BusinessContextInput(question_fa="گزارش", effective_at=NOW, journal_report_id=approved),
        )
    reports.review(
        b["owner"],
        b["business"],
        "reject",
        identity,
        ReportReview(approved=False, reviewed_values=True, reason_fa="شاهد نامعتبر"),
    )


def test_report_scope_isolation_immutability_and_database_review_policy(backend):
    b = backend
    _, reports, _, value = setup_report(b)
    identity = reports.create(b["owner"], b["business"], "report", value)
    with pytest.raises(AccessDenied):
        reports.create(b["viewer"], b["business"], "viewer", value)
    with pytest.raises(AccessDenied):
        reports.read(b["stranger"], b["business"], identity)
    with pytest.raises(NotFound):
        reports.read(b["stranger"], b["other"], identity)
    with pytest.raises(NotFound):
        reports.create(b["stranger"], b["other"], "cross", value)
    with b["db"].transaction(b["stranger"], b["other"]) as c:
        assert c.execute("SELECT * FROM herman.journal_reports").fetchall() == []
        assert c.execute("SELECT * FROM herman.journal_mappings").fetchall() == []
    with pytest.raises(psycopg.errors.InsufficientPrivilege), psycopg.connect(b["admin"]) as c:
        c.execute("UPDATE herman.journal_reports SET result='{}' WHERE id=%s", (identity,))
    with (
        pytest.raises(psycopg.errors.InsufficientPrivilege),
        b["db"].transaction(b["editor"], b["business"], write=True) as c,
    ):
        insert(
            c,
            "journal_report_decisions",
            dict(
                business_id=b["business"],
                report_id=identity,
                approved=True,
                reviewed_values=True,
                scope_confirmed=True,
                reason_fa="نامعتبر",
                created_by=b["editor"],
            ),
        )
    with (
        pytest.raises(psycopg.errors.CheckViolation),
        b["db"].transaction(b["owner"], b["business"], write=True) as c,
    ):
        insert(
            c,
            "journal_report_decisions",
            dict(
                business_id=b["business"],
                report_id=identity,
                approved=True,
                reviewed_values=True,
                scope_confirmed=False,
                reason_fa="نامعتبر",
                created_by=b["owner"],
            ),
        )


def test_report_over_limit_publishes_no_partial_values(backend, monkeypatch):
    b = backend
    _, reports, _, value = setup_report(b)
    monkeypatch.setattr(journal_reports, "MAX_LINES", 1)
    with pytest.raises(Conflict):
        reports.create(b["owner"], b["business"], "too-large", value)
    assert reports.page(b["owner"], b["business"], "reports") == []
    with b["db"].transaction(b["owner"], b["business"]) as c:
        assert not c.execute("SELECT 1 FROM herman.idempotency_keys WHERE key='too-large'").fetchone()


def test_absent_report_selector_preserves_existing_case_request_shape():
    value = BusinessContextInput(question_fa="پرسش", effective_at=NOW)
    assert value.model_dump(mode="json") == dict(
        question_fa="پرسش",
        effective_at="2026-10-10T00:00:00Z",
        knowledge_keys=[],
        analysis_id=None,
        include_financial=False,
    )
    selected = BusinessContextInput(question_fa="پرسش", effective_at=NOW, journal_report_id=uuid4())
    assert "journal_report_id" in selected.model_dump(mode="json")


def test_report_api_and_case_draft_receive_reviewed_summary_only(backend):
    b = backend
    _, reports, _, value = setup_report(b)
    seen = []

    class Stub:
        def advise(self, context):
            seen.append(context)
            return dict(text_fa="پیش‌نویس بررسی نقد", model="stub")

    headers = {"Authorization": "Bearer " + b["tokens"][0], "Idempotency-Key": "api-report"}
    base = f"/businesses/{b['business']}"
    with TestClient(create_app(b["db"], b["blob_root"], draft_agent=Stub())) as client:
        assert client.get(base + "/journal/reports").status_code == 401
        response = client.post(base + "/journal/reports", headers=headers, json=value.model_dump(mode="json"))
        assert response.status_code == 201, response.text
        identity = response.json()["id"]
        response = client.post(
            base + f"/journal/reports/{identity}/decision",
            headers={**headers, "Idempotency-Key": "approve-api"},
            json=report_review().model_dump(mode="json"),
        )
        assert response.status_code == 201, response.text
        case = client.post(
            base + "/advisor/cases",
            headers={**headers, "Idempotency-Key": "case"},
            json=dict(title_fa="بررسی گزارش نقد"),
        ).json()["id"]
        context = BusinessContextInput(
            question_fa="نقد چقدر است؟", effective_at=NOW, journal_report_id=UUID(identity)
        )
        response = client.post(
            base + f"/advisor/cases/{case}/turns",
            headers={**headers, "Idempotency-Key": "turn"},
            json=dict(expected_turn=0, generate_draft=True, context=context.model_dump(mode="json")),
        )
        assert response.status_code == 201, response.text
        assert response.headers["cache-control"] == "no-store" and len(seen) == 1
        assert seen[0]["journal"]["report_id"] == identity and "manifest" not in seen[0]["journal"]
        assert response.json()["request"]["context"]["journal_report_id"] == identity
        assert client.get(base + "/journal/reports", headers=headers).json()[0]["id"] == identity
