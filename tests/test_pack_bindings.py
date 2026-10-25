from datetime import datetime, timedelta, timezone
from uuid import uuid4

import psycopg
import pytest
from test_backend import backend as backend_fixture
from test_backend import database as database_fixture

from src.backend.database import AccessDenied
from src.backend.inventory import Count, Fulfillment, Item, Recipe, UnitConversion
from src.backend.pack_bindings import BindingCheckInput, BindingReviewInput, PackBindings
from src.backend.service import Conflict, NotFound, Warehouse

backend = backend_fixture
database = database_fixture


@pytest.fixture
def pending(backend):
    b = backend
    s = b["service"]
    documents = {}
    for role in ("record", "definition", "review"):
        documents[role] = s.document(b["owner"], b["business"], "doc:"+role, f"{role}.txt", "text/plain", role.encode())
    warehouse = Warehouse(id=uuid4(), business_id=b["business"], name="انبار")
    item = Item(id=uuid4(), business_id=b["business"], sku="PACK", name_fa="کالای بسته‌ای", base_unit="each")
    s.catalog(b["owner"], b["business"], "warehouse", warehouse)
    s.catalog(b["owner"], b["business"], "item", item)
    event = datetime.now(timezone.utc)-timedelta(days=2)
    record = Count(id=uuid4(), business_id=b["business"], warehouse_id=warehouse.id, item_id=item.id,
                   occurred_at=event, quantity="1", unit="pack",
                   evidence=dict(document_id=documents["record"], locator="line:1"))
    s.propose(b["editor"], b["business"], "record", record)
    with b["db"].transaction(b["owner"], b["business"]) as c:
        check = c.execute("SELECT id FROM herman.pack_binding_checks WHERE record_id=%s", (record.id,)).fetchone()["id"]
    factor = UnitConversion(id=uuid4(), business_id=b["business"], item_id=item.id, base_quantity="8",
                            evidence=dict(document_id=documents["definition"], locator="line:1"))
    s.catalog(b["owner"], b["business"], "factor", factor)
    return b, PackBindings(s), record, check, factor, documents


def review_value(factor, documents, approved=True):
    return BindingReviewInput(id=uuid4(), approved=approved, definition_id=factor.id if approved else None,
                              reason_fa="تبدیل تاریخی با شاهد بررسی شد",
                              evidence=dict(document_id=documents["review"], locator="line:1"))


def test_late_baseline_needs_review_and_check_receipt_stays_immutable(pending):
    b, bindings, record, check, factor, documents = pending
    original = bindings.read(b["viewer"], b["business"], check)
    assert original["effective_state"] == "unresolved"
    assert original["check"]["definition_id"] is None
    assert original["check"]["missing_reason"] == "missing_definition"
    capture = BindingCheckInput(id=uuid4(), record_id=record.id)
    assert bindings.capture(b["editor"], b["business"], "capture", capture) == check
    assert bindings.capture(b["editor"], b["business"], "capture", capture) == check
    decision = review_value(factor, documents)
    assert bindings.resolve(b["owner"], b["business"], "resolve", check, decision) == decision.id
    assert bindings.resolve(b["owner"], b["business"], "resolve", check, decision) == decision.id
    current = bindings.read(b["viewer"], b["business"], check)
    assert current["effective_state"] == "bound"
    assert current["check"] == original["check"]
    assert current["resolution"]["definition_id"] == factor.id
    assert current["resolution"]["document_id"] == documents["review"]
    assert bindings.page(b["viewer"], b["business"], record=record.id)["checks"][0]["resolution_id"] == decision.id
    assert len(bindings.reviews(b["viewer"], b["business"], check)["reviews"]) == 1
    with b["db"].transaction(b["owner"], b["business"]) as c:
        assert c.execute("SELECT count(*) AS n FROM herman.audit_events WHERE action='pack_binding.reviewed'").fetchone()["n"] == 1


@pytest.mark.parametrize("source", ["record", "definition", "review"])
def test_approval_verifies_all_evidence_and_rejection_remains_available(pending, source):
    b, bindings, _, check, factor, documents = pending
    with b["db"].transaction(b["owner"], b["business"]) as c:
        digest = c.execute("SELECT sha256 FROM herman.documents WHERE id=%s", (documents[source],)).fetchone()["sha256"]
    (b["blob_root"]/str(b["business"])/digest).write_bytes(b"changed")
    with pytest.raises(Conflict):
        bindings.resolve(b["owner"], b["business"], "resolve", check, review_value(factor, documents))
    assert bindings.reviews(b["viewer"], b["business"], check)["reviews"] == []
    bindings.resolve(b["owner"], b["business"], "reject", check, review_value(factor, documents, approved=False))
    assert bindings.read(b["viewer"], b["business"], check)["effective_state"] == "unresolved"
    assert bindings.reviews(b["viewer"], b["business"], check)["reviews"][0]["approved"] is False


def test_binding_review_and_history_respect_roles_and_tenant(pending):
    b, bindings, record, check, factor, documents = pending
    with pytest.raises(AccessDenied):
        bindings.capture(b["viewer"], b["business"], "capture", BindingCheckInput(id=uuid4(), record_id=record.id))
    with pytest.raises(AccessDenied):
        bindings.resolve(b["editor"], b["business"], "resolve", check, review_value(factor, documents))
    with pytest.raises(AccessDenied):
        bindings.read(b["stranger"], b["business"], check)
    with pytest.raises(NotFound):
        bindings.read(b["stranger"], b["other"], check)


def test_recipe_checks_keep_fulfillment_identity_and_reject_invalid_path(pending):
    b, bindings, record, _, _, documents = pending
    s = b["service"]
    product = Item(id=uuid4(), business_id=b["business"], sku="MEAL", name_fa="غذا", base_unit="each",
                   consumption_mode="recipe")
    s.catalog(b["owner"], b["business"], "product", product)
    recipe = Recipe(id=uuid4(), business_id=b["business"], product_id=product.id,
                    valid_from=record.occurred_at-timedelta(days=1), output_quantity="1", output_unit="each",
                    lines=[dict(item_id=record.item_id, quantity="1", unit="pack")],
                    evidence=dict(document_id=documents["record"], locator="recipe:1"))
    s.propose(b["editor"], b["business"], "recipe", recipe)
    checks = []
    for index in range(2):
        fulfillment = Fulfillment(id=uuid4(), business_id=b["business"], warehouse_id=record.warehouse_id,
                                  product_id=product.id, occurred_at=record.occurred_at, quantity="1", unit="each",
                                  evidence=dict(document_id=documents["record"], locator=f"order:{index}"))
        s.propose(b["editor"], b["business"], f"order:{index}", fulfillment)
        value = BindingCheckInput(id=uuid4(), record_id=recipe.id, ingredient_id=record.item_id,
                                   fulfillment_id=fulfillment.id, recipe_path=(recipe.id,))
        identity = bindings.capture(b["editor"], b["business"], f"capture:{index}", value)
        checks.append(bindings.read(b["viewer"], b["business"], identity)["check"])
    assert len({row["fulfillment_id"] for row in checks}) == 2
    assert all(row["item_id"] == record.item_id and row["occurred_at"] == record.occurred_at for row in checks)
    with pytest.raises(psycopg.errors.CheckViolation):
        bindings.capture(b["editor"], b["business"], "bad-path",
                         value.model_copy(update={"id": uuid4(), "recipe_path": (recipe.id, recipe.id)}))
