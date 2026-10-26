"""Managed-analysis completeness metadata cannot be omitted or self-certified."""

import hashlib
from copy import deepcopy

import pytest
from test_backend import backend as backend_fixture
from test_backend import database as database_fixture
from test_backend import inventory_payload as inventory_fixture
from test_backend import seed_inventory

from src.backend.coverage_models import CoverageSnapshot
from src.backend.inventory_freshness import advice_summary, freshness
from src.backend.service import canonical

backend = backend_fixture
database = database_fixture
inventory_payload = inventory_fixture


def receipt(b, value, key="managed"):
    identity = b["service"].analyze(b["owner"], b["business"], key, value)
    return b["service"].analysis(b["viewer"], b["business"], identity)


def rehash(row):
    row["input_sha256"] = hashlib.sha256(canonical(row["input_snapshot"]).encode()).hexdigest()
    return row


def test_true_declaration_is_retained_but_cannot_replace_review(backend, inventory_payload):
    b = backend
    value = seed_inventory(b, inventory_payload, attest=False)
    saved = receipt(b, value)
    raw = saved["input_snapshot"]
    assert all(raw["coverage_declaration"][name] for name in (
        "movements_complete", "fulfillment_complete", "recipes_complete"))
    assert not any(raw["coverage"][name] for name in (
        "movements_complete", "fulfillment_complete", "recipes_complete"))
    state = CoverageSnapshot.model_validate(raw["coverage_review"])
    assert state.assessment is state.decision is None
    assert not state.complete
    assert saved["result"]["status"] == "incomplete" and saved["pack_uses"] == []
    assert all(saved["result"][field] is None for field in (
        "expected_usage", "expected_closing", "counted_closing", "unexplained_shortage",
        "variance_fraction", "materiality_threshold", "needs_review"))
    assert any("ارزیابی" in reason for reason in saved["result"]["missing_fa"])
    assert rehash(deepcopy(saved))["input_sha256"] == saved["input_sha256"]


def test_legacy_receipt_keeps_raw_result_but_has_unknown_current_completeness(backend, inventory_payload):
    b = backend
    value = seed_inventory(b, inventory_payload)
    original = receipt(b, value)
    legacy = deepcopy(original)
    legacy["input_snapshot"].pop("coverage_review")
    legacy["input_snapshot"].pop("coverage_declaration")
    rehash(legacy)
    with b["db"].transaction(b["viewer"], b["business"]) as c:
        summary = advice_summary(c, b["business"], legacy)
    assert summary["freshness"]["reason"] == "legacy_coverage_missing"
    assert summary["freshness"]["status"] == "unknown"
    assert not summary["available_for_current_advice"]
    assert summary["result"] is None and summary["pack_uses"] == []
    assert legacy["result"] == original["result"] and original["result"]["status"] == "complete"
    assert b["service"].analysis(b["viewer"], b["business"], original["id"]) == original


@pytest.mark.parametrize("change", ["derived_flags", "scope", "basis", "version", "pending_count"])
def test_invalid_completeness_metadata_never_claims_current(backend, inventory_payload, change):
    b = backend
    value = seed_inventory(b, inventory_payload, attest=False)
    original = receipt(b, value)
    invalid = deepcopy(original)
    snapshot = invalid["input_snapshot"]
    if change == "derived_flags":
        snapshot["coverage"]["movements_complete"] = True
    elif change == "scope":
        snapshot["coverage_review"]["scope"]["warehouse_id"] = "00000000-0000-0000-0000-000000000001"
    elif change == "basis":
        snapshot["coverage_review"]["basis"] = "production"
    elif change == "version":
        snapshot["coverage_review"]["contract_version"] = "inventory.coverage.v999"
    else:
        snapshot["coverage_review"]["dataset"].pop("unreviewed_count")
    rehash(invalid)
    with b["db"].transaction(b["viewer"], b["business"]) as c:
        status = freshness(c, b["business"], invalid)
        summary = advice_summary(c, b["business"], invalid)
    assert status["status"] == "unknown"
    assert summary["result"] is None and not summary["available_for_current_advice"]
    assert b["service"].analysis(b["viewer"], b["business"], original["id"]) == original
