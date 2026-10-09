"""Persistent case boundaries, history handling and concurrent publication."""

# ruff: noqa: E402
import hashlib
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest

psycopg = pytest.importorskip("psycopg")
pytest.importorskip("fastapi")
from fastapi.testclient import TestClient
from test_backend import backend as backend_fixture
from test_backend import database as database_fixture

from src.backend.advisor import BusinessAdvisor
from src.backend.api import create_app
from src.backend.cases import BusinessCases, CaseInput, TurnInput
from src.backend.database import AccessDenied
from src.backend.service import Conflict, NotFound, canonical

backend = backend_fixture
database = database_fixture


def prepare(b):
    cases = BusinessCases(b["service"], BusinessAdvisor(b["service"]))
    identity = cases.create(b["owner"], b["business"], "case", CaseInput(title_fa="بررسی اختلاف انبار"))
    return cases, identity


def turn(number=0, generate=False):
    return TurnInput(
        expected_turn=number,
        generate_draft=generate,
        context=dict(question_fa="اختلاف از کجاست؟", effective_at="2026-10-09T00:00:00Z"),
    )


def unused(context):
    pytest.fail("context-only turn must not call a model")


def draft(context):
    return dict(
        status="draft",
        verified=False,
        context=context,
        context_sha256=hashlib.sha256(canonical(context).encode()).hexdigest(),
        draft=dict(text_fa="ادعای تأییدنشده: ۹۹۹ کیلو", model="test-only"),
    )


def test_case_retries_and_immutable_receipts(backend):
    b = backend
    cases, identity = prepare(b)
    assert (
        cases.create(b["owner"], b["business"], "case", CaseInput(title_fa="بررسی اختلاف انبار")) == identity
    )
    first = cases.append(b["owner"], b["business"], identity, "first", turn(), unused)
    assert cases.append(b["owner"], b["business"], identity, "first", turn(), unused) == first
    record = cases.read(b["viewer"], b["business"], identity, first)
    receipt = record["receipt"]
    assert receipt["status"] == "context_only" and receipt["persisted"]
    assert receipt["context_sha256"] == hashlib.sha256(canonical(receipt["context"]).encode()).hexdigest()
    assert cases.page(b["viewer"], b["business"])[0]["latest_turn"] == 1
    with pytest.raises(Conflict):
        cases.append(b["owner"], b["business"], identity, "first", turn(1), unused)
    with pytest.raises(psycopg.errors.InsufficientPrivilege), psycopg.connect(b["admin"]) as c:
        c.execute("UPDATE herman.advisor_turns SET receipt='{}' WHERE business_id=%s", (b["business"],))
    with b["db"].transaction(b["owner"], b["business"]) as c:
        assert (
            c.execute(
                "SELECT count(*) AS n FROM herman.audit_events WHERE action='case.turn_created'"
            ).fetchone()["n"]
            == 1
        )


def test_bounded_history_does_not_become_confirmed_knowledge(backend):
    b = backend
    cases, identity = prepare(b)
    last = None
    for n in range(5):
        last = cases.append(b["owner"], b["business"], identity, str(n), turn(n, True), draft)
    result = cases.read(b["owner"], b["business"], identity, last)["receipt"]["context"]
    history = result["conversation_history_unverified"]
    assert [h["turn_number"] for h in history] == [2, 3, 4]
    assert all(not h["authoritative"] for h in history)
    assert result["history_truncated"] and result["history_used"]
    assert result["knowledge"] == [] and result["analysis"] is None and result["financial"] is None
    with b["db"].transaction(b["owner"], b["business"]) as c:
        assert c.execute("SELECT count(*) AS n FROM herman.knowledge_claims").fetchone()["n"] == 0
    page = cases.turns(b["viewer"], b["business"], identity, after=2, limit=2)
    assert [r["turn_number"] for r in page] == [3, 4]
    assert all("receipt" not in r for r in page)


def test_replay_never_repeats_generation(backend):
    b = backend
    cases, identity = prepare(b)
    saved = cases.append(b["owner"], b["business"], identity, "key", turn(0, True), draft)
    assert cases.append(b["owner"], b["business"], identity, "key", turn(0, True), unused) == saved


def test_roles_and_cross_tenant_access_before_generation(backend):
    b = backend
    cases, identity = prepare(b)
    with pytest.raises(AccessDenied):
        cases.append(b["viewer"], b["business"], identity, "x", turn(0, True), unused)
    with pytest.raises(AccessDenied):
        cases.page(b["stranger"], b["business"])
    with pytest.raises(NotFound):
        cases.append(b["stranger"], b["other"], identity, "x", turn(0, True), unused)
    with b["db"].transaction(b["stranger"], b["other"]) as c:
        assert c.execute("SELECT * FROM herman.advisor_cases").fetchall() == []
        assert c.execute("SELECT * FROM herman.advisor_turns").fetchall() == []
    with (
        pytest.raises(psycopg.errors.ForeignKeyViolation),
        b["db"].transaction(b["stranger"], b["other"], write=True) as c,
    ):
        c.execute(
            "INSERT INTO herman.advisor_turns(business_id,id,case_id,turn_number,request,receipt,created_by) "
            "VALUES(%s,%s,%s,1,'{}','{}',%s)",
            (b["other"], uuid4(), identity, b["stranger"]),
        )


def test_stale_turn_rejected_and_failed_inference_publishes_nothing(backend):
    b = backend
    cases, identity = prepare(b)

    def fail(context):
        raise TimeoutError("model unavailable")

    with pytest.raises(TimeoutError):
        cases.append(b["owner"], b["business"], identity, "retry", turn(0, True), fail)
    assert cases.turns(b["owner"], b["business"], identity) == []
    cases.append(b["owner"], b["business"], identity, "retry", turn(0, True), draft)
    with pytest.raises(Conflict):
        cases.append(b["owner"], b["business"], identity, "stale", turn(0, True), unused)


def test_concurrent_continuations_have_one_winner(backend):
    b = backend
    cases, identity = prepare(b)
    barrier = Barrier(2)

    def wait_draft(context):
        barrier.wait(timeout=15)
        return draft(context)

    def append(key):
        try:
            return cases.append(b["owner"], b["business"], identity, key, turn(0, True), wait_draft)
        except (Conflict, psycopg.errors.UniqueViolation):
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(append, ["a", "b"]))
    assert sum(r is not None for r in results) == 1
    assert len(cases.turns(b["owner"], b["business"], identity)) == 1


def test_membership_removed_during_inference_prevents_publish(backend):
    b = backend
    cases, identity = prepare(b)

    def revoke(context):
        with psycopg.connect(b["admin"]) as c:
            c.execute(
                "DELETE FROM herman.memberships WHERE business_id=%s AND user_id=%s",
                (b["business"], b["editor"]),
            )
        return draft(context)

    with pytest.raises(AccessDenied):
        cases.append(b["editor"], b["business"], identity, "revoked", turn(0, True), revoke)
    assert cases.turns(b["owner"], b["business"], identity) == []


def test_case_api_without_model_and_no_quick_persistence(backend):
    b = backend
    headers = {"Authorization": "Bearer " + b["tokens"][0], "Idempotency-Key": "create-api"}
    base = f"/businesses/{b['business']}/advisor/cases"
    with TestClient(create_app(b["db"], b["blob_root"])) as client:
        assert client.post(base, json=dict(title_fa="پرونده")).status_code == 401
        response = client.post(base, json=dict(title_fa="پرونده"), headers=headers)
        assert response.status_code == 201, response.text
        case = response.json()["id"]
        response = client.post(
            base + f"/{case}/turns",
            json=turn().model_dump(mode="json"),
            headers={**headers, "Idempotency-Key": "turn-api"},
        )
        assert response.status_code == 201, response.text
        saved = response.json()
        assert saved["turn_number"] == 1 and saved["receipt"]["persisted"]
        assert response.headers["cache-control"] == "no-store"
        response = client.get(base + f"/{case}/turns/{saved['id']}", headers=headers)
        assert response.status_code == 200 and response.json() == saved
        assert client.get(base, headers=headers).json()[0]["latest_turn"] == 1
        assert (
            client.post("/quick/advisor/cases", json=dict(title_fa="x"), headers=headers).status_code == 404
        )


def test_revoked_credential_after_inference_does_not_publish(backend):
    b = backend
    cases, identity = prepare(b)

    class RevokingModel:
        def advise(self, context):
            with psycopg.connect(b["admin"]) as c:
                c.execute("UPDATE herman.api_credentials SET revoked=true WHERE user_id=%s", (b["owner"],))
            return dict(text_fa="پیش‌نویس", model="test-only")

    with TestClient(create_app(b["db"], b["blob_root"], draft_agent=RevokingModel())) as client:
        response = client.post(
            f"/businesses/{b['business']}/advisor/cases/{identity}/turns",
            json=turn(0, True).model_dump(mode="json"),
            headers={"Authorization": "Bearer " + b["tokens"][0], "Idempotency-Key": "revoked"},
        )
        assert response.status_code == 401, response.text
    assert cases.turns(b["owner"], b["business"], identity) == []
