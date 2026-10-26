"""Current selection versus immutable inventory receipts, exercised on PostgreSQL."""

# ruff: noqa: E402
import hashlib
from copy import deepcopy
from datetime import timedelta
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
from test_inventory_corrections import analyze, correct, review, revised

from src.backend import inventory_freshness
from src.backend.advisor import BusinessAdvisor, BusinessContextInput
from src.backend.api import create_app
from src.backend.cases import BusinessCases, CaseInput, TurnInput
from src.backend.database import AccessDenied
from src.backend.inventory import Count, Item, Movement, Recipe, UnitConversion
from src.backend.service import NotFound, Warehouse, canonical

backend = backend_fixture
database = database_fixture
inventory_payload = inventory_fixture


def view(b, receipt):
    return b["service"].analysis_view(b["viewer"], b["business"], receipt["id"])


def compare(b, receipt):
    return view(b, receipt)["freshness"]


def context(b, value, receipt):
    return BusinessAdvisor(b["service"]).context(b["viewer"], b["business"], BusinessContextInput(
        question_fa="وضعیت اختلاف موجودی چیست؟", effective_at=value.scope.end, analysis_id=receipt["id"]))


def add_movement(b, payload, **changes):
    value = Movement.model_validate(dict(payload["movements"][0], id=str(uuid4()), **changes))
    b["service"].propose(b["editor"], b["business"], str(value.id), value)
    return value


@pytest.mark.parametrize("kind,expected", [("count", "0"), ("movement", "27000"),
                                           ("recipe", "27000"), ("fulfillment", "19000")])
def test_reviewed_replacement_changes_freshness_but_never_the_receipt(backend, inventory_payload, kind, expected):
    b = backend
    value = seed_inventory(b, inventory_payload)
    original = analyze(b, value, "original")
    assert compare(b, original)["status"] == "current"
    change = dict(quantity={"count": "25", "movement": "70", "fulfillment": "900"}.get(kind))
    if kind == "recipe":
        change = dict(lines=[{**inventory_payload["recipes"][0]["lines"][0], "quantity": "0.1"}])
    predecessor, replacement = revised(inventory_payload, kind, **change)
    identity = correct(b, predecessor, replacement)
    assert compare(b, original)["status"] == "current"
    review(b, identity)
    status = compare(b, original)
    assert status["status"] == "stale" and status["stale"] is True
    assert status["changes"]["removed"]["count"] == 1
    assert status["changes"]["removed"]["examples"][0]["superseded_by"] == str(identity)
    assert status["changes"]["changed"]["count"] == 0
    assert status["changes"]["added"]["count"] == (0 if kind == "count" else 1)
    if kind == "count":
        assert status["count_selection_required"] == [dict(role="closing", id=str(predecessor),
                                                         superseded_by=str(identity))]
        value = value.model_copy(update={"closing_id": identity})
    else:
        assert status["count_selection_required"] == []
    assert b["service"].analysis(b["viewer"], b["business"], original["id"]) == original
    live = view(b, original)
    assert {k: v for k, v in live.items() if k != "freshness"} == original
    ctx = context(b, value, original)
    assert ctx["analysis"]["result"] is None
    assert not ctx["analysis"]["available_for_current_advice"]
    assert ctx["analysis"]["source_provenance"] == ctx["analysis"]["correction_provenance"] == []
    assert ctx["explanation_fa"] == status["reason_fa"]
    overview = BusinessAdvisor(b["service"]).overview(b["viewer"], b["business"], value.scope.end)
    preview = overview["recent_inventory_analyses"][0]
    assert preview["status"] == "stale" and preview["saved_status"] == "complete"
    assert preview["needs_review"] is preview["unexplained_shortage"] is None
    # Same idempotency key returns the original receipt even though it is now stale.
    initial_value = value.model_copy(update={"closing_id": original["input_snapshot"]["closing"]["id"]})
    assert b["service"].analyze(b["owner"], b["business"], "original", initial_value) == original["id"]
    fresh = analyze(b, value, "new-analysis")
    assert Decimal(fresh["result"]["unexplained_shortage"]) == Decimal(expected)
    assert compare(b, fresh)["status"] == "current"
    assert context(b, value, fresh)["analysis"]["available_for_current_advice"]


@pytest.mark.parametrize("kind", ["movement", "recipe", "fulfillment"])
def test_replacement_outside_scope_reports_removal_without_reinstating_original(backend, inventory_payload, kind):
    b = backend
    value = seed_inventory(b, inventory_payload)
    before = analyze(b, value, "before")
    change = dict(valid_from=value.scope.end) if kind == "recipe" else dict(occurred_at=value.scope.end)
    predecessor, replacement = revised(inventory_payload, kind, **change)
    review(b, correct(b, predecessor, replacement))
    status = compare(b, before)
    assert status["changes"]["removed"]["count"] == 1
    assert status["changes"]["added"]["count"] == 0
    assert status["status"] == "stale"


def test_replacement_moved_into_scope_is_an_addition(backend, inventory_payload):
    b = backend
    value = seed_inventory(b, inventory_payload)
    outside = add_movement(b, inventory_payload, occurred_at=value.scope.end, quantity="2")
    review(b, outside.id)
    before = analyze(b, value, "before")
    inside = outside.model_copy(update={"id": uuid4(), "occurred_at": value.scope.start + timedelta(days=1)})
    review(b, correct(b, outside.id, inside), "review-inside")
    status = compare(b, before)
    assert status["changes"]["added"]["examples"] == [dict(collection="movements", id=str(inside.id))]
    assert status["changes"]["removed"]["count"] == 0


@pytest.mark.parametrize("approve", [True, False])
def test_independent_pending_record_and_review_are_detected(backend, inventory_payload, approve):
    b = backend
    value = seed_inventory(b, inventory_payload)
    before = analyze(b, value, "before")
    pending = add_movement(b, inventory_payload, quantity="2")
    assert compare(b, before)["changes"]["added"]["count"] == 1
    incomplete = analyze(b, value, "pending")
    assert incomplete["result"]["status"] == "incomplete"
    assert compare(b, incomplete)["status"] == "current"
    assert not context(b, value, incomplete)["analysis"]["available_for_current_advice"]
    review(b, pending.id, approved=approve)
    status = compare(b, incomplete)
    assert status["status"] == "stale"
    if approve:
        assert status["changes"]["changed"]["examples"] == [dict(collection="movements", id=str(pending.id),
            before_status="proposed", after_status="approved", fields=["status"])]
    else:
        assert status["changes"]["removed"]["examples"][0]["superseded_by"] is None
        # Rejecting an independent candidate returns the earlier approved selection to its original state.
        assert compare(b, before)["status"] == "current"


@pytest.mark.parametrize("position,stale", [("before", False), ("start", True), ("end", False), ("warehouse", False)])
def test_half_open_period_and_warehouse_boundaries(backend, inventory_payload, position, stale):
    b = backend
    value = seed_inventory(b, inventory_payload)
    before = analyze(b, value, "before")
    change = dict(quantity="2", occurred_at={"before": value.scope.start - timedelta(microseconds=1),
                                           "end": value.scope.end}.get(position, value.scope.start))
    if position == "warehouse":
        warehouse = Warehouse(id=uuid4(), business_id=b["business"], name="انبار دوم")
        b["service"].catalog(b["owner"], b["business"], "other-warehouse", warehouse)
        change["warehouse_id"] = warehouse.id
    add_movement(b, inventory_payload, **change)
    assert compare(b, before)["stale"] is stale


@pytest.mark.parametrize("kind", ["items", "conversions", "recipes"])
def test_all_selected_catalog_and_recipe_inputs_are_compared_conservatively(backend, inventory_payload, kind):
    b = backend
    value = seed_inventory(b, inventory_payload)
    before = analyze(b, value, "before")
    if kind == "items":
        item = Item(id=uuid4(), business_id=b["business"], sku="unused", name_fa="کالای دیگر", base_unit="each")
        b["service"].catalog(b["owner"], b["business"], "new-item", item)
    elif kind == "conversions":
        conversion = UnitConversion(id=uuid4(), business_id=b["business"], item_id=value.target_item_id,
                                    base_quantity="500", evidence=value.coverage.evidence)
        b["service"].catalog(b["owner"], b["business"], "new-conversion", conversion)
    else:
        recipe = Recipe.model_validate(dict(inventory_payload["recipes"][0], id=str(uuid4())))
        b["service"].propose(b["editor"], b["business"], "overlap", recipe)
    status = compare(b, before)
    assert status["status"] == "stale"
    assert any(example["collection"] == kind for example in status["changes"]["added"]["examples"])


def test_rejected_corrections_new_counts_and_unrelated_evidence_do_not_invalidate_selection(backend, inventory_payload):
    b = backend
    value = seed_inventory(b, inventory_payload)
    before = analyze(b, value, "before")
    predecessor, replacement = revised(inventory_payload, "movement", quantity="70")
    review(b, correct(b, predecessor, replacement), approved=False)
    count = Count.model_validate(dict(inventory_payload["closing"], id=str(uuid4()), quantity="17"))
    b["service"].propose(b["editor"], b["business"], "another-count", count)
    b["service"].document(b["editor"], b["business"], "another-file", "note.txt", "text/plain", b"new evidence")
    b["service"].catalog(b["stranger"], b["other"], "other-item",
        Item(id=uuid4(), business_id=b["other"], sku="unrelated", name_fa="کالا", base_unit="each"))
    assert compare(b, before)["status"] == "current"


def test_explicit_count_successor_chain_and_missing_count_are_not_auto_selected(backend, inventory_payload):
    b = backend
    value = seed_inventory(b, inventory_payload)
    before = analyze(b, value, "before")
    predecessor, first = revised(inventory_payload, "count", quantity="20")
    review(b, correct(b, predecessor, first))
    second = first.model_copy(update={"id": uuid4(), "quantity": Decimal("21")})
    review(b, correct(b, first.id, second, "second"), "review-second")
    assert compare(b, before)["count_selection_required"][0]["superseded_by"] == str(second.id)
    missing = analyze(b, value.model_copy(update={"opening_id": None, "closing_id": None}), "no-counts")
    assert compare(b, missing)["status"] == "current"
    assert missing["result"]["status"] == "incomplete"


@pytest.mark.parametrize("limit", ["rows", "bytes"])
def test_bounds_yield_unknown_and_withhold_current_advice(backend, inventory_payload, monkeypatch, limit):
    b = backend
    value = seed_inventory(b, inventory_payload)
    before = analyze(b, value, "before")
    if limit == "rows":
        exact_rows = compare(b, before)["current_inputs"] + sum(
            len(recipe["lines"]) for recipe in before["input_snapshot"]["recipes"])
        monkeypatch.setattr(inventory_freshness, "MAX_INPUT_ROWS", exact_rows)
        assert compare(b, before)["status"] == "current"
        add_movement(b, inventory_payload, quantity="2")
    else:
        monkeypatch.setattr(inventory_freshness, "MAX_INPUT_BYTES", 1)
    status = compare(b, before)
    assert status["status"] == "unknown" and status["stale"] is None and status["changes"] is None
    ctx = context(b, value, before)
    assert ctx["analysis"]["result"] is None
    assert not ctx["analysis"]["available_for_current_advice"]


def test_changed_examples_are_bounded_but_totals_are_exact(backend, inventory_payload):
    b = backend
    value = seed_inventory(b, inventory_payload)
    before = analyze(b, value, "before")
    for n in range(21):
        add_movement(b, inventory_payload, quantity=str(n + 1))
    changes = compare(b, before)["changes"]["added"]
    assert changes["count"] == 21 and len(changes["examples"]) == 20 and changes["truncated"]


@pytest.mark.parametrize("fault,reason", [("hash", "input_hash_mismatch"), ("version", "unsupported_metric_version"),
                                         ("shape", "invalid_or_unsupported_input")])
def test_untrusted_or_unsupported_receipts_never_claim_current(backend, inventory_payload, fault, reason):
    b = backend
    value = seed_inventory(b, inventory_payload)
    row = deepcopy(analyze(b, value, "before"))
    if fault == "hash":
        row["input_snapshot"]["opening"]["quantity"] = "900"
    elif fault == "version":
        row["result"]["metric_version"] = "future"
    else:
        row["input_snapshot"] = {}
        row["input_sha256"] = hashlib.sha256(canonical({}).encode()).hexdigest()
    with b["db"].transaction(b["viewer"], b["business"]) as c:
        status = inventory_freshness.freshness(c, b["business"], row)
    assert status["status"] == "unknown" and status["reason"] == reason


def test_read_does_not_recompute_rewrite_or_reverify_files_and_respects_access(backend, inventory_payload, monkeypatch):
    b = backend
    value = seed_inventory(b, inventory_payload)
    before = analyze(b, value, "before")
    from src.backend import service
    monkeypatch.setattr(service, "reconcile_bound_inventory", lambda *_: pytest.fail("read must not recalculate"))
    with b["db"].transaction(b["viewer"], b["business"]) as c:
        source = c.execute("SELECT sha256 FROM herman.documents WHERE id=%s", (value.coverage.evidence.document_id,)).fetchone()
        audit_count = c.execute("SELECT count(*) AS n FROM herman.audit_events").fetchone()["n"]
    (b["blob_root"] / str(b["business"]) / source["sha256"]).write_bytes(b"changed file")
    status = compare(b, before)
    assert status["status"] == "current" and status["evidence_verification"] == "not_rechecked"
    with pytest.raises(AccessDenied):
        b["service"].analysis_view(b["stranger"], b["business"], before["id"])
    with pytest.raises(NotFound):
        b["service"].analysis_view(b["stranger"], b["other"], before["id"])
    with b["db"].transaction(b["viewer"], b["business"]) as c:
        assert c.execute("SELECT count(*) AS n FROM herman.audit_events").fetchone()["n"] == audit_count
    assert b["service"].analysis(b["viewer"], b["business"], before["id"]) == before


def test_api_returns_live_status_beside_historical_receipt(backend, inventory_payload):
    b = backend
    value = seed_inventory(b, inventory_payload)
    before = analyze(b, value, "before")
    add_movement(b, inventory_payload, quantity="2")
    with TestClient(create_app(b["db"], b["blob_root"])) as client:
        url = f"/businesses/{b['business']}/inventory-analyses/{before['id']}"
        assert client.get(url).status_code == 401
        response = client.get(url, headers={"Authorization": "Bearer " + b["tokens"][3]})
        assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
        assert response.json()["freshness"]["status"] == "stale"
        assert response.json()["result"] == before["result"]
        assert response.json()["input_snapshot"] == before["input_snapshot"]


def test_saved_case_context_remains_exact_while_next_turn_gets_stale_status(backend, inventory_payload):
    b = backend
    value = seed_inventory(b, inventory_payload)
    before = analyze(b, value, "before")
    cases = BusinessCases(b["service"], BusinessAdvisor(b["service"]))
    identity = cases.create(b["owner"], b["business"], "case", CaseInput(title_fa="بررسی موجودی"))
    request = TurnInput(expected_turn=0, generate_draft=False, context=BusinessContextInput(question_fa="اختلاف چقدر است؟",
        effective_at=value.scope.end, analysis_id=before["id"]))
    def unused(_):
        pytest.fail("context-only turn must not call inference")
    first = cases.append(b["owner"], b["business"], identity, "first", request, unused)
    saved = cases.read(b["viewer"], b["business"], identity, first)
    assert saved["receipt"]["context"]["analysis"]["freshness"]["status"] == "current"
    add_movement(b, inventory_payload, quantity="2")
    second = cases.append(b["owner"], b["business"], identity, "second",
                          request.model_copy(update={"expected_turn": 1}), unused)
    assert cases.read(b["viewer"], b["business"], identity, first) == saved
    current = cases.read(b["viewer"], b["business"], identity, second)["receipt"]["context"]["analysis"]
    assert current["freshness"]["status"] == "stale" and current["result"] is None


@pytest.mark.parametrize("position,stale", [("ends_at_start", False), ("starts_at_end", False),
                                           ("overlaps", True)])
def test_recipe_interval_boundaries(backend, inventory_payload, position, stale):
    b = backend
    value = seed_inventory(b, inventory_payload)
    before = analyze(b, value, "before")
    fields = dict(inventory_payload["recipes"][0], id=str(uuid4()))
    if position == "ends_at_start":
        fields.update(valid_from=value.scope.start-timedelta(days=1), valid_to=value.scope.start)
    else:
        fields.update(valid_from=value.scope.end-timedelta(microseconds=1) if stale else value.scope.end)
    b["service"].propose(b["editor"], b["business"], "recipe", Recipe.model_validate(fields))
    assert compare(b, before)["stale"] is stale


def test_equivalent_decimals_dates_and_order_do_not_invalidate_old_snapshots(backend, inventory_payload):
    b = backend
    value = seed_inventory(b, inventory_payload)
    row = deepcopy(analyze(b, value, "before"))
    row["input_snapshot"]["items"].reverse()
    row["input_snapshot"]["movements"].reverse()
    row["input_snapshot"]["opening"]["quantity"] = "100.000000"
    row["input_snapshot"]["opening"]["occurred_at"] = "2026-09-01T00:00:00+03:30"
    row["input_sha256"] = hashlib.sha256(canonical(row["input_snapshot"]).encode()).hexdigest()
    with b["db"].transaction(b["viewer"], b["business"]) as c:
        assert inventory_freshness.freshness(c, b["business"], row)["status"] == "current"


def test_comparison_uses_one_repeatable_read_snapshot(backend, inventory_payload, monkeypatch):
    b = backend
    value = seed_inventory(b, inventory_payload)
    before = analyze(b, value, "before")
    selector = inventory_freshness.select_inputs

    def insert_after_snapshot(c, business, scope, opening, closing, **kwargs):
        # The analysis read has established the snapshot; this separate transaction commits later.
        add_movement(b, inventory_payload, quantity="2")
        return selector(c, business, scope, opening, closing, **kwargs)

    monkeypatch.setattr(inventory_freshness, "select_inputs", insert_after_snapshot)
    assert compare(b, before)["status"] == "current"
    monkeypatch.setattr(inventory_freshness, "select_inputs", selector)
    assert compare(b, before)["status"] == "stale"


@pytest.mark.parametrize("fault", ["shape", "scope", "quantity"])
def test_malformed_result_is_unknown_and_summary_has_no_figures(backend, inventory_payload, fault):
    b = backend
    value = seed_inventory(b, inventory_payload)
    row = deepcopy(analyze(b, value, "before"))
    if fault == "shape":
        row["result"] = None
    elif fault == "scope":
        row["result"]["target_item_id"] = str(uuid4())
    else:
        row["result"]["unexplained_shortage"] = "not a quantity"
    with b["db"].transaction(b["viewer"], b["business"]) as c:
        summary = inventory_freshness.advice_summary(c, b["business"], row)
    assert summary["freshness"]["status"] == "unknown"
    assert summary["result"] is None and not summary["available_for_current_advice"]
