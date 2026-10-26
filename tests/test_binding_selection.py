"""Trusted SQL metadata, bounded reads and server-derived batch capture."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import psycopg
import pytest
from test_backend import backend as backend_fixture
from test_backend import database as database_fixture
from test_pack_bindings import pending as pending_fixture
from test_pack_bindings import review_value

from src.backend import pack_binding_selection
from src.backend.inventory import Count, Fulfillment, Item, Recipe, Scope
from src.backend.inventory_selection import select_inputs
from src.backend.pack_binding_selection import SelectionLimit, capture_past_contexts, select_binding_state
from src.backend.pack_interpretation import PackContext, PackInterpreter
from src.backend.pack_selection import pack_timeline

backend = backend_fixture
database = database_fixture
pending = pending_fixture


def selected(b, record, roots=()):
    with b["db"].transaction(b["viewer"], b["business"]) as c:
        definitions = pack_timeline(c, b["business"], record.item_id)
        return definitions, select_binding_state(c, b["business"], definitions, [record.id], roots)


def test_loading_late_definition_does_not_resolve_an_existing_check(pending):
    b, bindings, record, check, factor, documents = pending
    definitions, state = selected(b, record)
    context = PackContext(record_id=record.id, item_id=record.item_id, occurred_at=record.occurred_at)
    assert state.contract_version == "inventory.pack_bindings.v1"
    assert state.as_of >= state.checks[0].captured_at >= state.cutover_at
    assert state.checks[0].id == check and state.checks[0].state == "unresolved"
    assert not state.legacy_record_ids and not state.resolutions
    assert PackInterpreter(definitions, state).normalize(record.quantity, "pack", "each", context) is None
    bindings.resolve(b["owner"], b["business"], "reject", check, review_value(factor, documents, approved=False))
    assert not selected(b, record)[1].resolutions
    decision = review_value(factor, documents)
    bindings.resolve(b["owner"], b["business"], "approve", check, decision)
    definitions, current = selected(b, record)
    assert current.checks == state.checks
    assert current.resolutions[0].id == decision.id
    assert current.resolutions[0].evidence == decision.evidence
    assert PackInterpreter(definitions, current).normalize(record.quantity, "pack", "each", context) == (8, "each")


def test_total_metadata_budget_counts_observation_check_and_clock(pending, monkeypatch):
    b, _, record, _, _, _ = pending
    monkeypatch.setattr(pack_binding_selection, "MAX_BINDING_ROWS", 3)
    assert len(selected(b, record)[1].checks) == 1
    monkeypatch.setattr(pack_binding_selection, "MAX_BINDING_ROWS", 2)
    with pytest.raises(SelectionLimit):
        selected(b, record)


def test_supplied_reader_shares_its_remaining_budget(pending):
    b, _, record, _, _, _ = pending
    with b["db"].transaction(b["viewer"], b["business"]) as c:
        definitions = pack_timeline(c, b["business"], record.item_id)
        remaining = 2

        def read(query, parameters):
            nonlocal remaining
            rows = c.execute(query + " LIMIT %s", (*parameters, remaining + 1)).fetchall()
            remaining -= len(rows)
            if remaining < 0:
                raise SelectionLimit("shared budget exhausted")
            return rows

        with pytest.raises(SelectionLimit):
            select_binding_state(c, b["business"], definitions, [record.id], (), read=read)


def test_unbounded_base_selection_still_limits_binding_queries(pending):
    b, _, record, _, _, _ = pending
    scope = Scope(business_id=b["business"], warehouse_id=record.warehouse_id,
                  start=record.occurred_at, end=record.occurred_at + timedelta(days=1))
    observed = []
    with b["db"].transaction(b["viewer"], b["business"]) as c:
        class ObservedConnection:
            def execute(self, query, parameters):
                if isinstance(query, str) and any(name in query for name in (
                    "pack_definition_observations", "pack_binding_checks", "pack_binding_reviews",
                    "pack_binding_cutover", "AND pack_binding_legacy",
                )):
                    observed.append(query)
                    assert " LIMIT %s" in query
                return c.execute(query, parameters)

        result = select_inputs(ObservedConnection(), b["business"], scope, record.id, None, max_rows=None)
    assert observed and result["pack_bindings"]["checks"][0]["record_id"] == record.id


def test_scoped_metadata_reads_do_not_leak_another_business(pending):
    b, _, record, _, _, _ = pending
    definitions, _ = selected(b, record)
    with b["db"].transaction(b["stranger"], b["other"]) as c:
        hidden = select_binding_state(c, b["business"], definitions, [record.id], ())
        assert hidden.checks == hidden.resolutions == hidden.observations == hidden.legacy_record_ids == ()
        with pytest.raises(ValueError):
            select_binding_state(c, b["other"], definitions, [record.id], ())


def test_batch_capture_preserves_checks_and_skips_future_sources(pending):
    b, _, record, check, _, _ = pending
    before = selected(b, record)[1]
    context = PackContext(record_id=record.id, item_id=record.item_id, occurred_at=record.occurred_at)
    with b["db"].transaction(b["editor"], b["business"], write=True) as c:
        capture_past_contexts(c, b["business"], [context, context], before.as_of)
    assert selected(b, record)[1].checks == before.checks
    assert before.checks[0].id == check
    future = Count.model_validate(dict(record.model_dump(), id=uuid4(),
                                       occurred_at=datetime.now(timezone.utc) + timedelta(days=1)))
    b["service"].propose(b["editor"], b["business"], "future", future)
    future_context = PackContext(record_id=future.id, item_id=future.item_id, occurred_at=future.occurred_at)
    with b["db"].transaction(b["editor"], b["business"], write=True) as c:
        capture_past_contexts(c, b["business"], [future_context], before.as_of)
    assert not selected(b, future)[1].checks
    with pytest.raises(psycopg.errors.InsufficientPrivilege), b["db"].transaction(
        b["viewer"], b["business"],
    ) as c:
        capture_past_contexts(c, b["business"], [context], before.as_of)


def test_batch_capture_keeps_recipe_root_identity_and_reader_filters_roots(pending):
    b, _, record, _, _, documents = pending
    service = b["service"]
    product = Item(id=uuid4(), business_id=b["business"], sku="MEAL", name_fa="غذا",
                   base_unit="each", consumption_mode="recipe")
    service.catalog(b["owner"], b["business"], "meal", product)
    recipe = Recipe(id=uuid4(), business_id=b["business"], product_id=product.id,
                    valid_from=record.occurred_at - timedelta(days=1), output_quantity="1", output_unit="each",
                    lines=[dict(item_id=record.item_id, quantity="1", unit="pack")],
                    evidence=dict(document_id=documents["record"], locator="recipe:1"))
    service.propose(b["editor"], b["business"], "recipe", recipe)
    roots, contexts = [], []
    for index in range(2):
        root = Fulfillment(id=uuid4(), business_id=b["business"], warehouse_id=record.warehouse_id,
                           product_id=product.id, occurred_at=record.occurred_at, quantity="1", unit="each",
                           evidence=dict(document_id=documents["record"], locator=f"order:{index}"))
        service.propose(b["editor"], b["business"], f"order:{index}", root)
        roots.append(root.id)
        contexts.append(PackContext(record_id=recipe.id, ingredient_id=record.item_id, item_id=record.item_id,
                                    fulfillment_id=root.id, recipe_path=(recipe.id,), occurred_at=root.occurred_at))
    with b["db"].transaction(b["editor"], b["business"], write=True) as c:
        capture_past_contexts(c, b["business"], [*contexts, contexts[0]], datetime.now(timezone.utc))
    with b["db"].transaction(b["viewer"], b["business"]) as c:
        definitions = pack_timeline(c, b["business"], record.item_id)
        state = select_binding_state(c, b["business"], definitions, [recipe.id, *roots], roots)
        assert {check.fulfillment_id for check in state.checks} == set(roots)
        assert len({check.id for check in state.checks}) == 2
        narrow = select_binding_state(c, b["business"], definitions, [recipe.id, *roots], roots[:1])
        assert len(narrow.checks) == 1 and narrow.checks[0].fulfillment_id == roots[0]
        assert narrow.checks[0].recipe_path == (recipe.id,)
    invalid = contexts[0].model_copy(update={"recipe_path": (recipe.id, recipe.id)})
    with pytest.raises(psycopg.errors.CheckViolation), b["db"].transaction(
        b["editor"], b["business"], write=True,
    ) as c:
        capture_past_contexts(c, b["business"], [invalid], datetime.now(timezone.utc))
