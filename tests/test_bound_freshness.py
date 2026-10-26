"""Binding metadata changes current context without changing saved analysis receipts."""

import hashlib
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from test_backend import backend as backend_fixture
from test_backend import database as database_fixture
from test_backend import inventory_payload as inventory_fixture
from test_backend import seed_inventory
from test_inventory_corrections import analyze, review
from test_pack_bindings import pending as pending_fixture
from test_pack_bindings import review_value

from src.backend.inventory import Count, InventoryRequest, reconcile_inventory
from src.backend.inventory_freshness import _index, advice_summary, freshness
from src.backend.service import AnalysisInput, canonical

backend = backend_fixture
database = database_fixture
inventory_payload = inventory_fixture
pending = pending_fixture


def compare(b, row):
    with b["db"].transaction(b["viewer"], b["business"]) as c:
        return freshness(c, b["business"], row)


def with_hash(row):
    row["input_sha256"] = hashlib.sha256(canonical(row["input_snapshot"]).encode()).hexdigest()
    return row


def test_index_ignores_only_clock_passage(inventory_payload):
    raw = deepcopy(inventory_payload)
    raw["conversions"] = []
    now = datetime.now(timezone.utc)
    raw["pack_bindings"] = dict(business_id=raw["scope"]["business_id"], as_of=now,
                                cutover_at=now - timedelta(days=1))
    before = _index(raw)
    raw["pack_bindings"]["as_of"] += timedelta(hours=1)
    assert _index(raw) == before
    raw["pack_bindings"]["legacy_record_ids"] = [raw["opening"]["id"]]
    assert _index(raw) != before


def test_unsupported_legacy_pack_context_needs_no_live_selection(inventory_payload, monkeypatch):
    from src.backend import inventory_freshness

    inventory_payload["opening"]["unit"] = "pack"
    request = InventoryRequest.model_validate(inventory_payload)
    row = with_hash(dict(input_snapshot=request.model_dump(mode="json"),
                         result=reconcile_inventory(request).model_dump(mode="json")))

    def unexpected_selection(*args, **kwargs):
        pytest.fail("legacy pack context must not be fabricated from current definitions")

    monkeypatch.setattr(inventory_freshness, "select_inputs", unexpected_selection)
    status = freshness(None, request.scope.business_id, row)
    assert status["status"] == "unknown" and status["reason"] == "legacy_pack_context_missing"


def test_legacy_no_pack_receipt_still_compares(backend, inventory_payload):
    b = backend
    value = seed_inventory(b, inventory_payload)
    original = analyze(b, value, "before")
    legacy = deepcopy(original)
    legacy["input_snapshot"].pop("pack_bindings")
    assert compare(b, with_hash(legacy))["status"] == "current"
    legacy["input_snapshot"].pop("pack_definitions")
    assert compare(b, with_hash(legacy))["status"] == "current"
    assert b["service"].analysis(b["viewer"], b["business"], original["id"]) == original


@pytest.fixture
def unresolved_analysis(pending):
    b, bindings, opening, check, factor, documents = pending
    review(b, opening.id, "opening-approved")
    closing = Count.model_validate(dict(opening.model_dump(), id=uuid4(), quantity="6", unit="each",
                                       occurred_at=opening.occurred_at + timedelta(days=1)))
    b["service"].propose(b["editor"], b["business"], "closing", closing)
    review(b, closing.id, "closing-approved")
    ref = dict(document_id=documents["review"], locator="coverage:1")
    value = AnalysisInput(scope=dict(business_id=b["business"], warehouse_id=opening.warehouse_id,
                                    start=opening.occurred_at, end=closing.occurred_at),
                          target_item_id=opening.item_id, opening_id=opening.id, closing_id=closing.id,
                          coverage=dict(movements_complete=True, fulfillment_complete=True,
                                        recipes_complete=True, evidence=ref),
                          policy=dict(absolute_base_quantity="0", relative_fraction="0", evidence=ref))
    before = analyze(b, value, "before-resolution")
    assert before["result"]["status"] == "incomplete"
    return b, bindings, check, factor, documents, value, before


def test_approved_resolution_invalidates_current_context_and_preserves_history(unresolved_analysis):
    b, bindings, check, factor, documents, value, before = unresolved_analysis
    assert compare(b, before)["status"] == "current"
    decision = review_value(factor, documents)
    bindings.resolve(b["owner"], b["business"], "resolve", check, decision)
    status = compare(b, before)
    assert status["status"] == "stale"
    assert dict(collection="binding_resolutions", id=str(decision.id)) in status["changes"]["added"]["examples"]
    with b["db"].transaction(b["viewer"], b["business"]) as c:
        assert advice_summary(c, b["business"], before)["result"] is None
    assert b["service"].analysis(b["viewer"], b["business"], before["id"]) == before
    current = analyze(b, value, "after-resolution")
    assert current["result"]["status"] == "complete"
    assert Decimal(current["result"]["unexplained_shortage"]) == 2
    assert current["pack_uses"][0]["resolution_id"] == str(decision.id)
    assert compare(b, current)["status"] == "current"


def test_rejected_resolution_does_not_change_numeric_selection(unresolved_analysis):
    b, bindings, check, factor, documents, _, before = unresolved_analysis
    bindings.resolve(b["owner"], b["business"], "reject", check, review_value(factor, documents, approved=False))
    assert compare(b, before)["status"] == "current"
    assert before["pack_uses"] == []


@pytest.mark.parametrize("keep_timeline", [True, False])
def test_legacy_pack_context_is_unknown_and_never_fabricated(unresolved_analysis, keep_timeline):
    b, _, _, _, _, _, original = unresolved_analysis
    legacy = deepcopy(original)
    legacy["input_snapshot"].pop("pack_bindings")
    if not keep_timeline:
        legacy["input_snapshot"].pop("pack_definitions")
    with_hash(legacy)
    status = compare(b, legacy)
    assert status["status"] == "unknown" and status["reason"] == "legacy_pack_context_missing"
    with b["db"].transaction(b["viewer"], b["business"]) as c:
        summary = advice_summary(c, b["business"], legacy)
    assert summary["result"] is None and summary["pack_uses"] == []
    assert b["service"].analysis(b["viewer"], b["business"], original["id"]) == original


def test_binding_reads_have_no_capture_or_audit_side_effect(unresolved_analysis):
    b, _, _, _, _, _, row = unresolved_analysis
    def counts():
        with b["db"].transaction(b["viewer"], b["business"]) as c:
            return tuple(c.execute(f"SELECT count(*) AS n FROM herman.{table}").fetchone()["n"]
                         for table in ("pack_binding_checks", "pack_binding_reviews", "audit_events"))
    before = counts()
    for _ in range(2):
        assert compare(b, row)["status"] == "current"
    assert counts() == before


@pytest.mark.parametrize("field,value", [("cutover_at", "2999-01-01T00:00:00Z"),
                                        ("contract_version", "inventory.pack_bindings.v999")])
def test_unsupported_or_contradictory_binding_metadata_is_unknown(backend, inventory_payload, field, value):
    b = backend
    analysis_input = seed_inventory(b, inventory_payload)
    row = deepcopy(analyze(b, analysis_input, "before"))
    row["input_snapshot"]["pack_bindings"][field] = value
    status = compare(b, with_hash(row))
    assert status["status"] == "unknown" and status["reason"] == "invalid_or_unsupported_input"
