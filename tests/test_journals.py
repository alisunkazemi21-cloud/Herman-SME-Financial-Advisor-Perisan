"""Exact journal arithmetic and real PostgreSQL posting boundaries."""

# ruff: noqa: E402
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

psycopg = pytest.importorskip("psycopg")
pytest.importorskip("fastapi")
from fastapi.testclient import TestClient
from test_backend import backend as backend_fixture
from test_backend import database as database_fixture

from src.backend.api import create_app
from src.backend.database import AccessDenied
from src.backend.journals import (
    AccountInput,
    JournalDates,
    JournalDecision,
    JournalInput,
    Journals,
    fingerprint,
)
from src.backend.service import Conflict, NotFound, insert
from src.ingestion.normalizer import to_jalali

backend = backend_fixture
database = database_fixture
DAY = date(2026, 10, 9)


def value(document=None, amount="100", day=DAY):
    ref = dict(document_id=document or uuid4(), locator="ردیف ۱")
    return dict(
        entry_date=day,
        jalali_date=to_jalali(day),
        description_fa="ثبت فروش روزانه",
        lines=[
            dict(account_code="1000", side="debit", amount=amount, evidence=ref),
            dict(account_code="4000", side="credit", amount=amount, evidence=ref),
        ],
    )


def review(approved=True, resolution=None):
    return JournalDecision(
        approved=approved,
        reviewed_values=True,
        reason_fa="مقادیر و شاهد بررسی شد",
        duplicate_resolution=resolution,
    )


def prepare(b):
    ledger = Journals(b["service"])
    for code, kind in [("1000", "asset"), ("1100", "asset"), ("3000", "equity"), ("4000", "revenue")]:
        ledger.account(
            b["owner"], b["business"], code, AccountInput(code=code, name_fa="حساب نمونه", kind=kind)
        )
    doc = b["service"].document(
        b["owner"], b["business"], "evidence", "journal.txt", "text/plain", b"test evidence"
    )
    return ledger, doc


@pytest.mark.parametrize(
    "problem", ["float", "zero", "nan", "precision", "unbalanced", "duplicate_account", "date"]
)
def test_journal_input_rejects_invalid_values(problem):
    payload = value()
    if problem == "duplicate_account":
        payload["lines"][1]["account_code"] = "1000"
    elif problem == "date":
        payload["jalali_date"] = "1400/01/01"
    else:
        payload["lines"][0]["amount"] = dict(
            float=1.0, zero="0", nan="NaN", precision="1.0000001", unbalanced="99"
        )[problem]
    with pytest.raises(ValueError):
        JournalInput(**payload)


def test_fingerprint_ignores_evidence_description_line_order_and_decimal_scale():
    original = JournalInput(**value(amount="100"))
    other = value(amount="100.000000")
    other["lines"].reverse()
    other["description_fa"] = "شرح جدید"
    assert fingerprint(original) == fingerprint(JournalInput(**other))
    assert fingerprint(original) != fingerprint(JournalInput(**value(amount="101")))
    with pytest.raises(ValueError):
        JournalDecision(approved=True, reviewed_values=False, reason_fa="نادرست")


def test_proposal_review_trace_and_trial_balance(backend):
    b = backend
    ledger, doc = prepare(b)
    opening = value(doc, day=date(2026, 10, 1))
    opening["lines"][1]["account_code"] = "3000"
    identity = ledger.propose(b["editor"], b["business"], "opening", JournalInput(**opening))
    assert ledger.trial_balance(b["viewer"], b["business"], DAY, DAY)["totals"]["approved_entries"] == 0
    with pytest.raises(AccessDenied):
        ledger.decide(b["editor"], b["business"], "unauthorized", identity, review())
    ledger.decide(b["owner"], b["business"], "approve-opening", identity, review())
    assert ledger.decide(b["owner"], b["business"], "approve-opening", identity, review()) == identity
    sale = value(doc, amount="90")
    sale["lines"][1]["amount"] = "100"
    sale["lines"].append(
        dict(account_code="1100", side="debit", amount="10", evidence=sale["lines"][0]["evidence"])
    )
    sale = JournalInput(**sale)
    second = ledger.propose(b["editor"], b["business"], "sale", sale)
    assert ledger.propose(b["editor"], b["business"], "sale", sale) == second
    ledger.decide(b["owner"], b["business"], "approve-sale", second, review())
    rejected = ledger.propose(b["editor"], b["business"], "rejected", JournalInput(**value(doc, "17")))
    ledger.decide(b["owner"], b["business"], "reject", rejected, review(False))
    result = ledger.trial_balance(b["viewer"], b["business"], DAY, DAY)
    accounts = {row["code"]: row for row in result["accounts"]}
    assert accounts["1000"]["opening_net"] == "100"
    assert accounts["1000"]["closing_net"] == "190"
    assert accounts["4000"]["closing_net"] == "-100"
    assert result["totals"] == dict(approved_entries=2, period_debit="100", period_credit="100")
    assert result["evidence_verified"] and str(doc) in result["evidence_sha256"]
    trace = ledger.read(b["viewer"], b["business"], second)
    assert trace["decision"]["approved"] and len(trace["lines"]) == 3
    assert all(isinstance(row["amount"], str) for row in trace["lines"])
    assert len(ledger.page(b["viewer"], b["business"], limit=2)) == 2
    assert [a["code"] for a in ledger.accounts(b["viewer"], b["business"], after="1100")] == ["3000", "4000"]


def test_large_decimals_remain_exact_in_database_and_trial_balance(backend):
    b = backend
    ledger, doc = prepare(b)
    amount = "9999999999999999999999.999999"
    identity = ledger.propose(b["owner"], b["business"], "large", JournalInput(**value(doc, amount)))
    ledger.decide(b["owner"], b["business"], "large-approved", identity, review())
    result = ledger.trial_balance(b["owner"], b["business"], DAY, DAY)
    assert result["totals"]["period_debit"] == amount
    assert result["accounts"][0]["closing_net"] == amount


def test_duplicates_require_explicit_review_and_concurrent_first_approval_has_one_winner(backend):
    b = backend
    ledger, doc = prepare(b)
    ids = [ledger.propose(b["editor"], b["business"], f"p{n}", JournalInput(**value(doc))) for n in range(2)]
    assert ledger.read(b["owner"], b["business"], ids[1])["duplicate_candidates"][0]["id"] == ids[0]

    def approve(identity):
        try:
            return ledger.decide(b["owner"], b["business"], str(identity), identity, review())
        except psycopg.IntegrityError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(approve, ids))
    assert sum(r is not None for r in results) == 1
    loser = ids[results.index(None)]
    ledger.decide(b["owner"], b["business"], "distinct", loser, review(resolution="distinct_event"))
    assert ledger.trial_balance(b["owner"], b["business"], DAY, DAY)["totals"]["period_debit"] == "200"


def test_reversals_require_approval_preserve_history_and_allow_rejected_retry(backend):
    b = backend
    ledger, doc = prepare(b)
    identity = ledger.propose(b["editor"], b["business"], "sale", JournalInput(**value(doc)))
    dates = JournalDates(entry_date=DAY, jalali_date=to_jalali(DAY), description_fa="برگشت سند اشتباه")
    with pytest.raises(Conflict):
        ledger.reverse(b["editor"], b["business"], "early", identity, dates)
    ledger.decide(b["owner"], b["business"], "approve", identity, review())
    first = ledger.reverse(b["editor"], b["business"], "reverse1", identity, dates)
    ledger.decide(b["owner"], b["business"], "reject-reversal", first, review(False))
    candidates = [
        ledger.reverse(b["editor"], b["business"], f"reverse-{n}", identity, dates) for n in range(2)
    ]
    ledger.decide(b["owner"], b["business"], "reverse-approved", candidates[0], review())
    with pytest.raises(psycopg.IntegrityError):
        ledger.decide(
            b["owner"], b["business"], "second-reverse", candidates[1], review(resolution="distinct_event")
        )
    with pytest.raises(Conflict):
        ledger.reverse(b["editor"], b["business"], "reverse-again", identity, dates)
    assert ledger.read(b["viewer"], b["business"], identity)["decision"]["approved"]
    result = ledger.trial_balance(b["viewer"], b["business"], DAY, DAY)
    assert all(Decimal(row["closing_net"]) == 0 for row in result["accounts"])
    assert result["totals"]["period_debit"] == result["totals"]["period_credit"] == "200"


def test_evidence_tampering_blocks_approval_trace_and_trial_balance(backend):
    b = backend
    ledger, doc = prepare(b)
    first = ledger.propose(b["owner"], b["business"], "p1", JournalInput(**value(doc)))
    second = ledger.propose(b["owner"], b["business"], "p2", JournalInput(**value(doc, "11")))
    ledger.decide(b["owner"], b["business"], "approve1", first, review())
    metadata, _ = b["service"].read_document(b["owner"], b["business"], doc)
    (b["blob_root"] / str(b["business"]) / metadata["sha256"]).write_bytes(b"changed")
    with pytest.raises(Conflict):
        ledger.decide(b["owner"], b["business"], "approve2", second, review())
    with pytest.raises(Conflict):
        ledger.read(b["viewer"], b["business"], first)
    with pytest.raises(Conflict):
        ledger.trial_balance(b["viewer"], b["business"], DAY, DAY)
    # A broken source can still be rejected; rejection does not post values.
    ledger.decide(b["owner"], b["business"], "reject", second, review(False))


def test_dated_reversal_and_database_rejection_of_inexact_inverse(backend):
    b = backend
    ledger, doc = prepare(b)
    identity = ledger.propose(b["owner"], b["business"], "original", JournalInput(**value(doc)))
    ledger.decide(b["owner"], b["business"], "approved", identity, review())
    bad = value(doc, "99")
    for line in bad["lines"]:
        line["side"] = "credit" if line["side"] == "debit" else "debit"
    with (
        pytest.raises(psycopg.errors.CheckViolation),
        b["db"].transaction(b["owner"], b["business"], write=True) as c,
    ):
        ledger._store(c, b["owner"], b["business"], JournalInput(**bad), identity)
    next_day = date(2026, 10, 10)
    reversal = ledger.reverse(
        b["owner"],
        b["business"],
        "reverse",
        identity,
        JournalDates(entry_date=next_day, jalali_date=to_jalali(next_day), description_fa="برگشت روز بعد"),
    )
    ledger.decide(b["owner"], b["business"], "reverse-approved", reversal, review())
    earlier = ledger.trial_balance(b["owner"], b["business"], DAY, DAY)
    assert earlier["accounts"][0]["closing_net"] == "100"
    later = ledger.trial_balance(b["owner"], b["business"], next_day, next_day)
    assert later["accounts"][0]["opening_net"] == "100"
    assert Decimal(later["accounts"][0]["closing_net"]) == 0
    with pytest.raises(Conflict):
        ledger.reverse(
            b["owner"],
            b["business"],
            "reverse-reversal",
            reversal,
            JournalDates(
                entry_date=next_day, jalali_date=to_jalali(next_day), description_fa="زنجیره نامعتبر"
            ),
        )


def test_trial_balance_refuses_account_truncation(backend):
    b = backend
    ledger, _ = prepare(b)
    with b["db"].transaction(b["owner"], b["business"], write=True) as c:
        c.execute(
            "INSERT INTO herman.journal_accounts(business_id,id,code,name_fa,kind,created_by) "
            "SELECT %s,gen_random_uuid(),'test_'||n,'حساب آزمون','asset',%s FROM generate_series(1,1001) n",
            (b["business"], b["owner"]),
        )
    with pytest.raises(Conflict):
        ledger.trial_balance(b["viewer"], b["business"], DAY, DAY)


def test_database_balance_sealing_immutability_and_pattern_constraints(backend):
    b = backend
    ledger, doc = prepare(b)
    proposal = JournalInput(**value(doc))
    identity = ledger.propose(b["owner"], b["business"], "valid", proposal)
    with (
        pytest.raises(psycopg.errors.CheckViolation),
        b["db"].transaction(b["owner"], b["business"], write=True) as c,
    ):
        insert(
            c,
            "journal_lines",
            dict(
                business_id=b["business"],
                entry_id=identity,
                line_number=3,
                account_code="1100",
                side="debit",
                amount=1,
                document_id=doc,
                locator="1",
                created_by=b["owner"],
            ),
        )
    with pytest.raises(psycopg.errors.InsufficientPrivilege), psycopg.connect(b["admin"]) as c:
        c.execute(
            "UPDATE herman.journal_entries SET description_fa='changed' WHERE business_id=%s",
            (b["business"],),
        )
    for problem in ("empty", "unbalanced", "pattern"):
        with (
            pytest.raises(psycopg.errors.CheckViolation),
            b["db"].transaction(b["owner"], b["business"], write=True) as c,
        ):
            entry = uuid4()
            insert(
                c,
                "journal_entries",
                dict(
                    business_id=b["business"],
                    id=entry,
                    entry_date=DAY,
                    jalali_date=to_jalali(DAY),
                    currency="IRR",
                    description_fa="آزمون قید",
                    event_fingerprint=fingerprint(proposal),
                    created_by=b["owner"],
                ),
            )
            if problem != "empty":
                for n, side, code, amount in [
                    (1, "debit", "1000", 99),
                    (2, "credit", "4000", 100 if problem == "unbalanced" else 99),
                ]:
                    insert(
                        c,
                        "journal_lines",
                        dict(
                            business_id=b["business"],
                            entry_id=entry,
                            line_number=n,
                            account_code=code,
                            side=side,
                            amount=amount,
                            document_id=doc,
                            locator="1",
                            created_by=b["owner"],
                        ),
                    )


def test_tenant_isolation_foreign_keys_and_viewer_rejection(backend):
    b = backend
    ledger, doc = prepare(b)
    identity = ledger.propose(b["editor"], b["business"], "p", JournalInput(**value(doc)))
    with pytest.raises(AccessDenied):
        ledger.propose(b["viewer"], b["business"], "viewer", JournalInput(**value(doc)))
    with pytest.raises(AccessDenied):
        ledger.read(b["stranger"], b["business"], identity)
    with pytest.raises(NotFound):
        ledger.read(b["stranger"], b["other"], identity)
    with b["db"].transaction(b["stranger"], b["other"]) as c:
        assert c.execute("SELECT * FROM herman.journal_entries").fetchall() == []
        assert c.execute("SELECT * FROM herman.journal_lines").fetchall() == []
    otherdoc = b["service"].document(b["stranger"], b["other"], "doc", "other.txt", "text/plain", b"other")
    with pytest.raises(NotFound):
        ledger.propose(b["owner"], b["business"], "cross-doc", JournalInput(**value(otherdoc)))
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        ledger.propose(b["stranger"], b["other"], "cross-account", JournalInput(**value(otherdoc)))
    with (
        pytest.raises(psycopg.errors.InsufficientPrivilege),
        b["db"].transaction(b["editor"], b["business"], write=True) as c,
    ):
        insert(
            c,
            "journal_decisions",
            dict(
                business_id=b["business"],
                entry_id=identity,
                approved=True,
                reviewed_values=True,
                reason_fa="تلاش نامعتبر",
                created_by=b["editor"],
            ),
        )


def test_journal_api_auth_validation_and_decimal_strings(backend):
    b = backend
    ledger, doc = prepare(b)
    base = f"/businesses/{b['business']}/journal"
    headers = {"Authorization": "Bearer " + b["tokens"][0], "Idempotency-Key": "api"}
    with TestClient(create_app(b["db"], b["blob_root"])) as client:
        assert client.get(base + "/accounts").status_code == 401
        response = client.post(
            base + "/entries",
            headers=headers,
            json=JournalInput(**value(doc, "1.123456")).model_dump(mode="json"),
        )
        assert response.status_code == 201, response.text
        identity = response.json()["id"]
        response = client.get(base + "/entries/" + identity, headers=headers)
        assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
        assert response.json()["lines"][0]["amount"] == "1.123456"
        response = client.post(
            base + f"/entries/{identity}/decision",
            headers={**headers, "Idempotency-Key": "api-review"},
            json=review().model_dump(mode="json"),
        )
        assert response.status_code == 201, response.text
        response = client.get(
            base + "/trial-balance", headers=headers, params=dict(start=DAY.isoformat(), end=DAY.isoformat())
        )
        assert response.json()["totals"]["period_debit"] == "1.123456"
        assert client.get(base + "/entries?limit=101", headers=headers).status_code == 422
