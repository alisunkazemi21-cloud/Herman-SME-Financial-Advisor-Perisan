"""Analysis writes persist interpretation identities before emitting numeric receipts."""

import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from threading import Barrier, local
from uuid import UUID, uuid4

import pytest
from test_backend import backend as backend_fixture
from test_backend import database as database_fixture
from test_backend import inventory_payload as inventory_fixture
from test_bound_freshness import unresolved_analysis as unresolved_fixture
from test_dated_inventory import dated_payload as dated_fixture
from test_inventory_corrections import analyze, review
from test_pack_bindings import pending as pending_fixture
from test_pack_bindings import review_value
from test_pack_integration import setup

from src.backend import service
from src.backend.inventory import Fulfillment, Item, Recipe
from src.backend.service import Conflict, canonical

backend = backend_fixture
database = database_fixture
inventory_payload = inventory_fixture
dated_payload = dated_fixture
pending = pending_fixture
unresolved_analysis = unresolved_fixture


@pytest.fixture
def recipe_context(unresolved_analysis):
    b, bindings, opening_check, factor, documents, value, _ = unresolved_analysis
    resolution_document = b["service"].document(b["owner"], b["business"], "resolution-only",
        "resolution-only.txt", "text/plain", b"separate historical interpretation evidence")
    resolution = review_value(factor, dict(documents, review=resolution_document))
    bindings.resolve(b["owner"], b["business"], "opening-resolution", opening_check, resolution)
    documents = dict(documents, resolution=resolution_document)
    product = Item(id=uuid4(), business_id=b["business"], sku="MEAL", name_fa="غذا",
                   base_unit="each", consumption_mode="recipe")
    b["service"].catalog(b["owner"], b["business"], "meal", product)
    evidence = dict(document_id=documents["record"], locator="recipe:1")
    recipe = Recipe(id=uuid4(), business_id=b["business"], product_id=product.id,
                    valid_from=value.scope.start - timedelta(days=1), output_quantity="1", output_unit="each",
                    lines=[dict(item_id=value.target_item_id, quantity="0.25", unit="pack")], evidence=evidence)
    b["service"].propose(b["editor"], b["business"], "recipe", recipe)
    review(b, recipe.id, "recipe-approved")
    root = Fulfillment(id=uuid4(), business_id=b["business"], warehouse_id=value.scope.warehouse_id,
                       product_id=product.id, occurred_at=value.scope.start + timedelta(hours=1),
                       quantity="1", unit="each", evidence=evidence)
    b["service"].propose(b["editor"], b["business"], "order", root)
    review(b, root.id, "order-approved")
    return b, bindings, factor, documents, value, recipe, root


def recipe_check(row, recipe):
    return next(check for check in row["input_snapshot"]["pack_bindings"]["checks"]
                if check["record_id"] == str(recipe.id))


def test_recipe_capture_is_saved_before_hash_and_resolution_controls_numbers(recipe_context):
    b, bindings, factor, documents, value, recipe, root = recipe_context
    before = analyze(b, value, "recipe-before")
    check = recipe_check(before, recipe)
    assert before["result"]["status"] == "incomplete" and before["pack_uses"] == []
    assert check["fulfillment_id"] == str(root.id) and check["recipe_path"] == [str(recipe.id)]
    assert check["state"] == "unresolved" and check["created_by"] == str(b["owner"])
    assert hashlib.sha256(canonical(before["input_snapshot"]).encode()).hexdigest() == before["input_sha256"]
    assert b["service"].analyze(b["owner"], b["business"], "recipe-before", value) == before["id"]
    decision = review_value(factor, documents)
    bindings.resolve(b["owner"], b["business"], "recipe-resolution", UUID(check["id"]), decision)
    current = analyze(b, value, "recipe-after")
    assert current["result"]["status"] == "complete"
    assert Decimal(current["result"]["expected_usage"]) == 2
    assert Decimal(current["result"]["unexplained_shortage"]) == 0
    use = next(use for use in current["pack_uses"] if use["record_id"] == str(recipe.id))
    assert use["check_id"] == check["id"] and use["resolution_id"] == str(decision.id)
    assert use["resolution_evidence"] == decision.evidence.model_dump(mode="json")
    assert use["context_version"] == "pack.use.v3" and use["interpretation"] == "reviewed"
    assert b["service"].analysis(b["viewer"], b["business"], before["id"]) == before


def test_source_tampering_rolls_back_new_recipe_capture_and_analysis(recipe_context):
    b, _, _, documents, value, recipe, _ = recipe_context
    with b["db"].transaction(b["viewer"], b["business"]) as c:
        digest = c.execute("SELECT sha256 FROM herman.documents WHERE id=%s", (documents["resolution"],)).fetchone()["sha256"]
    (b["blob_root"] / str(b["business"]) / digest).write_bytes(b"changed review source")
    with pytest.raises(Conflict):
        analyze(b, value, "tampered-analysis")
    with b["db"].transaction(b["viewer"], b["business"]) as c:
        assert not c.execute("SELECT 1 FROM herman.pack_binding_checks WHERE record_id=%s", (recipe.id,)).fetchone()
        assert not c.execute("SELECT 1 FROM herman.idempotency_keys WHERE key='tampered-analysis'").fetchone()


@pytest.mark.parametrize("limit", ["MAX_ANALYSIS_ROWS", "MAX_ANALYSIS_BYTES"])
def test_analysis_budget_exhaustion_has_no_partial_write(recipe_context, monkeypatch, limit):
    b, _, _, _, value, recipe, _ = recipe_context
    monkeypatch.setattr(service, limit, 1)
    with pytest.raises(ValueError):
        analyze(b, value, "over-budget")
    with b["db"].transaction(b["viewer"], b["business"]) as c:
        assert not c.execute("SELECT 1 FROM herman.pack_binding_checks WHERE record_id=%s", (recipe.id,)).fetchone()
        assert not c.execute("SELECT 1 FROM herman.idempotency_keys WHERE key='over-budget'").fetchone()


def test_concurrent_analysis_captures_one_shared_context(recipe_context, monkeypatch):
    b, _, _, _, value, recipe, _ = recipe_context
    barrier, attempts = Barrier(2), local()
    capture = service.capture_past_contexts

    def simultaneous(*args):
        if not getattr(attempts, "entered", False):
            attempts.entered = True
            barrier.wait(10)
        capture(*args)

    monkeypatch.setattr(service, "capture_past_contexts", simultaneous)
    with ThreadPoolExecutor(max_workers=2) as pool:
        rows = list(pool.map(lambda key: analyze(b, value, key), ("concurrent-a", "concurrent-b")))
    assert rows[0]["id"] != rows[1]["id"]
    assert len({recipe_check(row, recipe)["id"] for row in rows}) == 1
    assert all(row["result"]["status"] == "incomplete" and row["pack_uses"] == [] for row in rows)
    with b["db"].transaction(b["viewer"], b["business"]) as c:
        assert c.execute("SELECT count(*) AS n FROM herman.pack_binding_checks WHERE record_id=%s",
                         (recipe.id,)).fetchone()["n"] == 1


def test_future_to_past_boundary_rejects_an_uncaptured_receipt(backend, dated_payload, monkeypatch):
    b = backend
    _, value, _, _ = setup(b, dated_payload)
    select = service.select_inputs
    calls = 0

    def crossing(*args, **kwargs):
        nonlocal calls
        selected = select(*args, **kwargs)
        calls += 1
        if calls == 2:
            selected["pack_bindings"]["as_of"] = value.scope.end + timedelta(microseconds=1)
        return selected

    monkeypatch.setattr(service, "select_inputs", crossing)
    with pytest.raises(Conflict, match="دوباره"):
        analyze(b, value, "crossed-boundary")
    with b["db"].transaction(b["viewer"], b["business"]) as c:
        assert not c.execute("SELECT 1 FROM herman.analysis_runs").fetchone()
        assert not c.execute("SELECT 1 FROM herman.pack_binding_checks").fetchone()
        assert not c.execute("SELECT 1 FROM herman.idempotency_keys WHERE key='crossed-boundary'").fetchone()
