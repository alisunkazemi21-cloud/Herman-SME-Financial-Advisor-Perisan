"""C17 HTTP acceptance: reviewed evidence and investigation follow-up."""

import hashlib
import secrets
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from test_backend import backend as backend_fixture
from test_backend import database as database_fixture
from test_backend import inventory_payload as inventory_fixture
from test_backend import seed_inventory

from src.backend.api import create_app

backend = backend_fixture
database = database_fixture
inventory_payload = inventory_fixture

CATEGORIES = (
    "opening_count", "closing_count", "purchases", "sales", "returns", "transfers",
    "waste", "staff_meals", "complimentary", "production", "other_use", "recipes",
)


@pytest.fixture
def client(backend):
    with TestClient(create_app(backend["db"], backend["blob_root"])) as value:
        yield value


def headers(b, role="owner", key=None):
    index = {"owner": 0, "stranger": 1, "editor": 2, "viewer": 3}[role]
    result = {"Authorization": "Bearer " + b["tokens"][index]}
    if key is not None:
        result["Idempotency-Key"] = key
    return result


def checked(response, status=200):
    assert response.status_code == status, response.text
    assert response.headers["Cache-Control"] == "no-store"
    return response.json()


def post(client, b, path, payload, key, role="owner", status=201):
    return checked(client.post(path, json=payload, headers=headers(b, role, key)), status)


def coverage_payload(value):
    recorded = {"opening_count", "closing_count", "purchases", "sales", "waste", "recipes"}
    evidence = value.coverage.evidence.model_dump(mode="json")
    return dict(
        id=str(uuid4()), scope=value.scope.model_dump(mode="json"), basis=value.basis,
        categories={name: dict(status="records_complete" if name in recorded else "no_events",
                               evidence=evidence, note_fa="سوابق این دسته برای دورهٔ نمونه بررسی شد")
                    for name in CATEGORIES}, evidence=evidence,
    )


def reviewed_coverage(client, b, value):
    payload = coverage_payload(value)
    path = f"/businesses/{b['business']}/coverage"
    proposed = post(client, b, path, payload, "coverage-proposal", "editor")
    assert proposed["id"] == payload["id"]
    post(client, b, path + f"/{payload['id']}/decision",
         dict(approved=True, reason_fa="پوشش دوره با اسناد بررسی شد"), "coverage-review")
    return payload


def assessment(client, b, value):
    return checked(client.get(
        f"/businesses/{b['business']}/coverage/assessment",
        params=dict(warehouse_id=str(value.scope.warehouse_id), start=value.scope.start.isoformat(),
                    end=value.scope.end.isoformat(), basis=value.basis), headers=headers(b, "viewer"),
    ))


def analyze(client, b, value, key="analysis"):
    return post(client, b, f"/businesses/{b['business']}/inventory-analyses",
                value.model_dump(mode="json"), key)


def current_context(client, b, value, analysis_id):
    return post(client, b, f"/businesses/{b['business']}/advisor/context",
                dict(question_fa="این اختلاف به چه بررسی نیاز دارد؟", analysis_id=analysis_id,
                     effective_at=(value.scope.end + timedelta(days=1)).isoformat()),
                "context-only", status=200)["analysis"]


def action_payload(value, analysis_id):
    return dict(
        id=str(uuid4()), analysis_id=analysis_id, kind="record_missing",
        title_fa="بررسی ثبت مصرف کارکنان", detail_fa="مسئول شیفت سوابق مصرف ثبت‌نشده را بررسی کند",
        responsible_name_fa="مسئول شیفت", follow_up_at=(datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
        evidence=value.coverage.evidence.model_dump(mode="json"),
    )


def reviewer_headers(b):
    identity, token = uuid4(), secrets.token_urlsafe(48)
    with psycopg.connect(b["admin"]) as connection:
        connection.execute("INSERT INTO herman.users(id,display_name) VALUES(%s,%s)", (identity, "بازبین"))
        connection.execute("INSERT INTO herman.api_credentials(digest,user_id,expires_at) VALUES(%s,%s,%s)",
                           (hashlib.sha256(token.encode()).hexdigest(), identity,
                            datetime.now(timezone.utc) + timedelta(days=1)))
        connection.execute("INSERT INTO herman.memberships(business_id,user_id,role) VALUES(%s,%s,'reviewer')",
                           (b["business"], identity))
    return {"Authorization": "Bearer " + token}


def test_three_true_flags_cannot_replace_a_review(client, backend, inventory_payload):
    b = backend
    value = seed_inventory(b, inventory_payload, attest=False)
    assert value.coverage.movements_complete and value.coverage.fulfillment_complete and value.coverage.recipes_complete
    review = assessment(client, b, value)
    assert review["complete"] is False and review["blockers_fa"]
    assert review["snapshot"]["assessment"] is None
    saved = analyze(client, b, value)
    assert saved["result"]["status"] == "incomplete"
    assert saved["result"]["unexplained_shortage"] is None and saved["pack_uses"] == []


def test_reviewed_coverage_roundtrip_enables_independent_inventory_arithmetic(client, backend, inventory_payload):
    b = backend
    value = seed_inventory(b, inventory_payload, attest=False)
    proposal = reviewed_coverage(client, b, value)
    state = assessment(client, b, value)
    assert state["complete"] is True and state["provisional"] is False
    assert state["snapshot"]["decision"]["assessment_id"] == proposal["id"]
    path = f"/businesses/{b['business']}/coverage"
    detail = checked(client.get(path + "/" + proposal["id"], headers=headers(b, "viewer")))
    assert detail["assessment"] == {**proposal, "supersedes_id": None}
    assert detail["decision"]["approved"] is True
    page = checked(client.get(path, headers=headers(b, "viewer")))
    assert [row["id"] for row in page["assessments"]] == [proposal["id"]]
    saved = analyze(client, b, value)
    assert saved["result"]["status"] == "complete"
    # 100 kg + 50 kg - 5 kg waste - 1000 * .12 kg recipe - 18 kg closing = 7 kg.
    assert Decimal(saved["result"]["unexplained_shortage"]) == 7000
    assert Decimal(saved["result"]["expected_usage"]) == 120000
    assert proposal["id"] in str(saved["input_snapshot"])
    assert current_context(client, b, value, saved["id"])["available_for_current_advice"] is True


def test_pending_operational_record_invalidates_review_and_withholds_current_advice(client, backend, inventory_payload):
    b = backend
    value = seed_inventory(b, inventory_payload, attest=False)
    reviewed_coverage(client, b, value)
    saved = analyze(client, b, value)
    original = b["service"].analysis(b["owner"], b["business"], UUID(saved["id"]))
    pending = dict(inventory_payload["movements"][0], id=str(uuid4()), quantity="2")
    response = client.post(f"/businesses/{b['business']}/movements", json=pending,
                           headers=headers(b, "editor", "pending-operation"))
    assert response.status_code == 201, response.text
    assert assessment(client, b, value)["complete"] is False
    unsupported = analyze(client, b, value, "after-pending")
    assert unsupported["result"]["status"] == "incomplete"
    assert unsupported["result"]["unexplained_shortage"] is None
    context = current_context(client, b, value, saved["id"])
    assert context["available_for_current_advice"] is False
    assert context["result"] is None and context["pack_uses"] == []
    assert b["service"].analysis(b["viewer"], b["business"], UUID(saved["id"])) == original


def test_future_period_review_keeps_conditional_receipt_but_suppresses_current_figures(client, backend, inventory_payload):
    b = backend
    p = inventory_payload
    shift = datetime.now(timezone.utc) + timedelta(days=1) - datetime.fromisoformat(p["scope"]["start"])
    for name in ("start", "end"):
        p["scope"][name] = (datetime.fromisoformat(p["scope"][name]) + shift).isoformat()
    for row in [p["opening"], p["closing"], *p["movements"], *p["fulfillments"]]:
        row["occurred_at"] = (datetime.fromisoformat(row["occurred_at"]) + shift).isoformat()
    for row in p["recipes"]:
        row["valid_from"] = (datetime.fromisoformat(row["valid_from"]) + shift).isoformat()
    value = seed_inventory(b, p, attest=False)
    reviewed_coverage(client, b, value)
    status = assessment(client, b, value)
    assert status["complete"] is True and status["provisional"] is True
    saved = analyze(client, b, value)
    assert saved["result"]["status"] == "complete"
    assert Decimal(saved["result"]["unexplained_shortage"]) == 7000
    current = current_context(client, b, value, saved["id"])
    assert current["available_for_current_advice"] is False
    assert current["result"] is None and current["pack_uses"] == []
    params = dict(effective_at=(value.scope.end + timedelta(days=1)).isoformat())
    overview = checked(client.get(f"/businesses/{b['business']}/overview", params=params,
                                  headers=headers(b, "viewer")))
    portfolio = checked(client.get("/advisor/portfolio", params=params, headers=headers(b, "viewer")))
    assert len(portfolio["businesses"]) == 1
    for summary in (overview, portfolio["businesses"][0]):
        preview = summary["recent_inventory_analyses"][0]
        assert preview["id"] == saved["id"] and preview["saved_status"] == "complete"
        assert preview["available_for_current_advice"] is False
        assert preview["freshness"]["completeness"]["provisional"] is True
        assert preview["needs_review"] is None and preview["unexplained_shortage"] is None
    detail = checked(client.get(f"/businesses/{b['business']}/inventory-analyses/{saved['id']}",
                                headers=headers(b, "viewer")))
    assert detail["result"] == saved["result"]


def test_action_on_incomplete_analysis_retains_reviewed_inconclusive_history(client, backend, inventory_payload):
    b = backend
    value = seed_inventory(b, inventory_payload, attest=False)
    saved = analyze(client, b, value)
    assert saved["result"]["status"] == "incomplete"
    path = f"/businesses/{b['business']}/actions"
    payload = action_payload(value, saved["id"])
    identity = post(client, b, path, payload, "action", "editor")["id"]
    item_path = path + "/" + identity
    post(client, b, item_path + "/events", dict(kind="approve", expected_sequence=0,
         reason_fa="این بررسی برای تکمیل اسناد لازم است"), "action-approval")
    post(client, b, item_path + "/events", dict(kind="start", expected_sequence=1,
         reason_fa="سوابق شیفت بررسی می‌شود"), "action-start", "editor")
    event = dict(kind="complete", expected_sequence=2, reason_fa="شواهد برای نتیجهٔ قطعی کافی نبود",
                 outcome="inconclusive", evidence=payload["evidence"])
    completed = checked(client.post(item_path + "/events", json=event,
        headers={**reviewer_headers(b), "Idempotency-Key": "action-completion"}), 201)
    detail = checked(client.get(item_path, headers=headers(b, "viewer"), params=dict(limit=1)))
    assert detail["state"] == "completed" and detail["sequence"] == 3
    assert detail["proposal"]["title_fa"] == payload["title_fa"]
    assert detail["next_sequence"] == 1 and detail["events"][0]["kind"] == "approve"
    tail = checked(client.get(item_path, headers=headers(b, "viewer"), params=dict(after_sequence=1, limit=2)))
    assert [row["kind"] for row in tail["events"]] == ["start", "complete"]
    assert tail["events"][-1]["id"] == completed["id"]
    assert tail["events"][-1]["outcome"] == "inconclusive"
    assert not {"savings", "confirmed_savings", "cause"} & tail["events"][-1].keys()
    page = checked(client.get(path, headers=headers(b, "viewer")))
    assert page["proposals"][0]["id"] == identity
    unchanged = b["service"].analysis(b["viewer"], b["business"], UUID(saved["id"]))
    assert unchanged["result"] == saved["result"] and unchanged["result"]["unexplained_shortage"] is None


def test_coverage_and_action_routes_enforce_roles_and_business_boundaries(client, backend, inventory_payload):
    b = backend
    value = seed_inventory(b, inventory_payload, attest=False)
    coverage_path = f"/businesses/{b['business']}/coverage"
    proposal = coverage_payload(value)
    post(client, b, coverage_path, proposal, "forbidden-proposal", "viewer", 403)
    post(client, b, coverage_path, proposal, "proposal", "editor")
    post(client, b, coverage_path + f"/{proposal['id']}/decision",
         dict(approved=True, reason_fa="تأیید نامجاز"), "forbidden-review", "editor", 403)
    saved = analyze(client, b, value)
    action_path = f"/businesses/{b['business']}/actions"
    action = action_payload(value, saved["id"])
    post(client, b, action_path, action, "forbidden-action", "viewer", 403)
    post(client, b, action_path, action, "action", "editor")
    post(client, b, action_path + f"/{action['id']}/events",
         dict(kind="approve", expected_sequence=0, reason_fa="تأیید نامجاز"), "forbidden-event", "editor", 403)
    for collection, identity in (("coverage", proposal["id"]), ("actions", action["id"])):
        checked(client.get(f"/businesses/{b['business']}/{collection}/{identity}",
                           headers=headers(b, "stranger")), 403)
        checked(client.get(f"/businesses/{b['other']}/{collection}/{identity}",
                           headers=headers(b, "stranger")), 404)


def test_http_idempotency_reuses_proposals_events_and_rejects_changed_payloads(client, backend, inventory_payload):
    b = backend
    value = seed_inventory(b, inventory_payload, attest=False)
    path = f"/businesses/{b['business']}/coverage"
    payload = coverage_payload(value)
    first = post(client, b, path, payload, "same-coverage")
    assert post(client, b, path, payload, "same-coverage") == first
    changed = deepcopy(payload)
    changed["categories"]["sales"]["note_fa"] = "توضیح متفاوت"
    post(client, b, path, changed, "same-coverage", status=409)
    saved = analyze(client, b, value)
    action_path = f"/businesses/{b['business']}/actions"
    action = action_payload(value, saved["id"])
    first = post(client, b, action_path, action, "same-action")
    assert post(client, b, action_path, action, "same-action") == first
    event_path = action_path + f"/{first['id']}/events"
    event = dict(kind="approve", expected_sequence=0, reason_fa="شروع بررسی مجاز است")
    original = post(client, b, event_path, event, "same-event")
    assert post(client, b, event_path, event, "same-event") == original
    post(client, b, event_path, event, "different-key-old-sequence", status=409)
    with b["db"].transaction(b["owner"], b["business"]) as connection:
        assert connection.execute("SELECT count(*) AS n FROM herman.action_events").fetchone()["n"] == 1


def test_invalid_action_transitions_and_terminal_writes_are_rejected(client, backend, inventory_payload):
    b = backend
    value = seed_inventory(b, inventory_payload, attest=False)
    saved = analyze(client, b, value)
    path = f"/businesses/{b['business']}/actions"
    action = action_payload(value, saved["id"])
    post(client, b, path, action, "action")
    events = path + f"/{action['id']}/events"
    post(client, b, events, dict(kind="start", expected_sequence=0, reason_fa="هنوز تأیید نشده"),
         "start-before-approval", "editor", 409)
    post(client, b, events, dict(kind="approve", expected_sequence=0, reason_fa="بررسی تأیید شد"), "approve")
    post(client, b, events, dict(kind="complete", expected_sequence=1, reason_fa="فاقد شاهد نتیجه"),
         "complete-without-evidence", status=422)
    post(client, b, events, dict(kind="cancel", expected_sequence=1, reason_fa="این اقدام با اقدام دیگری جایگزین شد"),
         "cancel")
    post(client, b, events, dict(kind="note", expected_sequence=2, reason_fa="افزودن پس از لغو"),
         "after-terminal", "editor", 409)
    detail = checked(client.get(path + "/" + action["id"], headers=headers(b, "viewer")))
    assert detail["state"] == "cancelled" and detail["sequence"] == 2
    assert [row["kind"] for row in detail["events"]] == ["approve", "cancel"]


def test_validation_redacts_private_inputs_and_all_error_paths_are_no_store(client, backend, inventory_payload):
    b = backend
    value = seed_inventory(b, inventory_payload, attest=False)
    saved = analyze(client, b, value)
    coverage_path = f"/businesses/{b['business']}/coverage"
    action_path = f"/businesses/{b['business']}/actions"
    marker = "PRIVATE-RAW-CUSTOMER-INPUT-77419"
    coverage = coverage_payload(value)
    coverage["categories"].pop("closing_count")
    coverage["categories"]["sales"]["note_fa"] = marker
    action = action_payload(value, saved["id"])
    action.update(responsible_name_fa="", detail_fa=marker)
    for index, (path, payload) in enumerate(((coverage_path, coverage), (action_path, action))):
        response = client.post(path, json=payload, headers=headers(b, key=f"invalid-{index}"))
        assert checked(response, 422) == {"detail": "ورودی با قرارداد داده سازگار نیست"}
        assert marker not in response.text and "input" not in response.json()
    checked(client.get(coverage_path), 401)
    checked(client.get(action_path, headers=headers(b, "stranger")), 403)
    checked(client.get(coverage_path + "/" + str(uuid4()), headers=headers(b)), 404)
    checked(client.get(action_path, params=dict(limit=0), headers=headers(b)), 422)
    checked(client.get(coverage_path + "/assessment", params=dict(start=marker), headers=headers(b)), 422)


def test_tampered_coverage_evidence_cannot_be_approved_and_rejection_remains_possible(client, backend, inventory_payload):
    b = backend
    value = seed_inventory(b, inventory_payload, attest=False)
    path = f"/businesses/{b['business']}/coverage"
    payload = coverage_payload(value)
    post(client, b, path, payload, "proposal")
    document = value.coverage.evidence.document_id
    metadata, _ = b["service"].read_document(b["owner"], b["business"], document)
    (b["blob_root"] / str(b["business"]) / metadata["sha256"]).write_bytes(b"modified source")
    decision_path = path + f"/{payload['id']}/decision"
    post(client, b, decision_path, dict(approved=True, reason_fa="تأیید پس از تغییر فایل"), "tampered-approve", status=409)
    detail = checked(client.get(path + "/" + payload["id"], headers=headers(b, "viewer")))
    assert detail["decision"] is None
    post(client, b, decision_path, dict(approved=False, reason_fa="فایل شاهد قابل اتکا نیست"), "reject")
    detail = checked(client.get(path + "/" + payload["id"], headers=headers(b, "viewer")))
    assert detail["decision"]["approved"] is False
