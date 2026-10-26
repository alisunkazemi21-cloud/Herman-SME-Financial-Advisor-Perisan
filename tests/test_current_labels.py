"""Published dated labels in bounded selections and immutable analysis receipts."""

import hashlib
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError
from test_backend import backend as backend_fixture
from test_backend import database as database_fixture
from test_backend import inventory_payload as inventory_fixture
from test_backend import seed_inventory
from test_inventory_corrections import analyze

from src.backend import inventory_freshness, item_selection, service
from src.backend.catalog import Catalog, ItemDecision, ItemProposal
from src.backend.database import AccessDenied
from src.backend.inventory import Item
from src.backend.inventory_selection import select_inputs
from src.backend.item_selection import ItemLabel, ItemLabelState, resolve_sku, select_item_labels
from src.backend.pack_binding_selection import SelectionLimit
from src.backend.service import Conflict, canonical

backend = backend_fixture
database = database_fixture
inventory_payload = inventory_fixture


@pytest.fixture
def current_labels(backend, inventory_payload):
    b = backend
    # A prospective reporting instant permits a reviewed label activation in this scope.
    end = datetime.now(timezone.utc) + timedelta(days=2)
    inventory_payload["scope"]["end"] = end.isoformat()
    inventory_payload["closing"]["occurred_at"] = end.isoformat()
    value = seed_inventory(b, inventory_payload)
    item = Item.model_validate(inventory_payload["items"][0])
    document = b["service"].document(b["editor"], b["business"], "label-source", "label.txt",
                                     "text/plain", "نام جدید و کد جدید".encode())
    return b, value, item, document


def proposal(b, item, document, *, predecessor=None, suffix="NEW"):
    value = ItemProposal(id=uuid4(), item_id=item.id, predecessor_id=predecessor or item.id,
                         sku=suffix, name_fa="نام بررسی‌شده", evidence=dict(document_id=document, locator="line:1"))
    Catalog(b["service"]).propose_item(b["editor"], b["business"], str(value.id), value)
    return value


def decide(b, proposed, when=None, approved=True):
    return Catalog(b["service"]).decide_item(b["owner"], b["business"], "review:" + str(proposed.id),
        proposed.id, ItemDecision(approved=approved, effective_at=when, reason_fa="با شاهد بررسی شد"))


def at(b, item, when):
    with b["db"].transaction(b["viewer"], b["business"]) as c:
        return select_item_labels(c, b["business"], [item.id], when).labels[0]


def compare(b, row):
    with b["db"].transaction(b["viewer"], b["business"]) as c:
        return inventory_freshness.freshness(c, b["business"], row)


def rehash(row):
    row["input_sha256"] = hashlib.sha256(canonical(row["input_snapshot"]).encode()).hexdigest()
    return row


def test_pending_rejected_and_exact_half_open_selection_preserve_original(current_labels):
    b, value, item, document = current_labels
    baseline = at(b, item, value.scope.end)
    assert baseline.definition_id == item.id and baseline.decision == "baseline"
    assert baseline.evidence is baseline.approved_at is baseline.valid_from is None
    rejected = proposal(b, item, document, suffix="REJECTED")
    assert at(b, item, value.scope.end) == baseline
    decide(b, rejected, approved=False)
    assert at(b, item, value.scope.end) == baseline
    chosen = proposal(b, item, document)
    when = value.scope.end - timedelta(days=1)
    decide(b, chosen, when)
    assert at(b, item, when - timedelta(microseconds=1)).definition_id == item.id
    selected = at(b, item, when)
    assert selected.definition_id == chosen.id and selected.valid_from == when
    assert selected.approved_at <= when and selected.evidence == chosen.evidence
    with b["db"].transaction(b["viewer"], b["business"]) as c:
        assert resolve_sku(c, b["business"], item.sku, when - timedelta(microseconds=1))["definition_id"] == item.id
        assert resolve_sku(c, b["business"], chosen.sku, when)["definition_id"] == chosen.id
        with pytest.raises(ValueError):
            resolve_sku(c, b["business"], item.sku, when)
        raw = c.execute("SELECT * FROM herman.items WHERE id=%s", (item.id,)).fetchone()
        assert Item.model_validate(raw) == item


def test_analysis_uses_published_ids_and_source_without_rewriting_old_receipt(current_labels):
    b, value, item, document = current_labels
    before = analyze(b, value, "before")
    proposed = proposal(b, item, document)
    assert compare(b, before)["status"] == "current"
    decide(b, proposed, value.scope.end - timedelta(days=1))
    assert compare(b, before)["status"] == "stale"
    after = analyze(b, value, "after")
    state = ItemLabelState.model_validate(after["input_snapshot"]["item_labels"])
    chosen = next(row for row in state.labels if row.item_id == item.id)
    assert chosen.definition_id == proposed.id and chosen.evidence.document_id == document
    assert state.effective_at == value.scope.end
    assert next(row for row in after["input_snapshot"]["items"] if row["id"] == str(item.id))["sku"] == "NEW"
    assert after["result"] == before["result"]
    assert after["input_sha256"] != before["input_sha256"]
    assert rehash(deepcopy(after))["input_sha256"] == after["input_sha256"]
    assert compare(b, after)["status"] == "current"
    assert b["service"].analysis(b["viewer"], b["business"], before["id"]) == before
    assert b["service"].analyze(b["owner"], b["business"], "before", value) == before["id"]


def test_selected_label_source_tamper_prevents_new_analysis(current_labels):
    b, value, item, document = current_labels
    proposed = proposal(b, item, document)
    decide(b, proposed, value.scope.end - timedelta(days=1))
    before = analyze(b, value, "before")
    with b["db"].transaction(b["viewer"], b["business"]) as c:
        digest = c.execute("SELECT sha256 FROM herman.documents WHERE id=%s", (document,)).fetchone()["sha256"]
    source = b["blob_root"] / str(b["business"]) / digest
    assert hashlib.sha256(source.read_bytes()).hexdigest() == digest
    source.write_bytes(b"tampered label source")
    assert compare(b, before)["status"] == "current"
    with pytest.raises(Conflict, match="تغییر"):
        analyze(b, value, "tampered")
    with b["db"].transaction(b["viewer"], b["business"]) as c:
        assert not c.execute("SELECT 1 FROM herman.idempotency_keys WHERE key='tampered'").fetchone()
        assert c.execute("SELECT count(*) AS n FROM herman.analysis_runs").fetchone()["n"] == 1


@pytest.mark.parametrize("approved_first", [False, True])
def test_future_interval_end_alone_does_not_make_analysis_stale(current_labels, approved_first):
    b, value, item, document = current_labels
    predecessor = item.id
    if approved_first:
        first = proposal(b, item, document)
        decide(b, first, value.scope.end - timedelta(days=1))
        predecessor = first.id
    before = analyze(b, value, "before")
    next_label = proposal(b, item, document, predecessor=predecessor, suffix="FUTURE")
    decide(b, next_label, value.scope.end + timedelta(days=1))
    assert compare(b, before)["status"] == "current"
    assert b["service"].analysis(b["viewer"], b["business"], before["id"]) == before


def test_legacy_snapshot_compares_dated_text_without_fabricating_identity(current_labels):
    b, value, item, document = current_labels
    receipt = analyze(b, value, "before")
    legacy = deepcopy(receipt)
    legacy["input_snapshot"].pop("item_labels")
    rehash(legacy)
    assert compare(b, legacy)["status"] == "current"
    proposed = proposal(b, item, document)
    decide(b, proposed, value.scope.end - timedelta(days=1))
    stale = compare(b, legacy)
    assert stale["status"] == "stale"
    assert stale["changes"]["added"]["count"] == stale["changes"]["removed"]["count"] == 0
    assert stale["changes"]["changed"]["examples"] == [dict(collection="items", id=str(item.id),
        before_status=None, after_status=None, fields=["name_fa", "sku"])]


@pytest.mark.parametrize("fault", ["business", "instant", "missing", "text", "interval"])
def test_untrusted_label_state_never_claims_current(current_labels, fault):
    b, value, _, _ = current_labels
    receipt = deepcopy(analyze(b, value, "before"))
    state = receipt["input_snapshot"]["item_labels"]
    if fault == "business":
        state["business_id"] = str(uuid4())
    elif fault == "instant":
        state["effective_at"] = (value.scope.end + timedelta(seconds=1)).isoformat()
    elif fault == "missing":
        state["labels"].pop()
    elif fault == "text":
        state["labels"][0]["sku"] = "forged"
    else:
        state["labels"][0]["valid_to"] = value.scope.end.isoformat()
    assert compare(b, rehash(receipt))["reason"] == "invalid_or_unsupported_input"


def test_labels_share_physical_read_budget_and_standalone_limit(current_labels, monkeypatch):
    b, value, item, _ = current_labels
    with b["db"].transaction(b["viewer"], b["business"]) as c:
        queries = []

        class ObservedConnection:
            def execute(self, query, parameters):
                if isinstance(query, str) and "item_alias_periods" in query:
                    queries.append((query, parameters))
                    assert " LIMIT %s" in query
                return c.execute(query, parameters)

        selected = select_inputs(ObservedConnection(), b["business"], value.scope,
                                value.opening_id, value.closing_id, max_rows=None)
        assert len(queries) == 1 and queries[0][1][-1] == 10001
        assert len(selected["item_labels"]["labels"]) == len(selected["items"])
        with pytest.raises(SelectionLimit):
            select_inputs(c, b["business"], value.scope, value.opening_id, value.closing_id,
                          max_rows=len(selected["items"]))
        monkeypatch.setattr(item_selection, "MAX_LABEL_ROWS", 1)
        with pytest.raises(SelectionLimit):
            select_item_labels(c, b["business"], (uuid4() for _ in range(2)), value.scope.end)
        with pytest.raises(ValueError):
            select_item_labels(c, b["business"], [uuid4()], value.scope.end)
        assert select_item_labels(c, b["business"], [], value.scope.end).labels == ()
        assert at(b, item, value.scope.end).item_id == item.id


def test_reader_roles_and_rls_never_fallback_to_other_tenant(current_labels):
    b, value, item, document = current_labels
    for actor in ("owner", "editor", "viewer"):
        with b["db"].transaction(b[actor], b["business"]) as c:
            assert select_item_labels(c, b["business"], [item.id], value.scope.end).labels[0].item_id == item.id
    with b["db"].transaction(b["stranger"], b["other"]) as c:
        with pytest.raises(ValueError):
            select_item_labels(c, b["business"], [item.id], value.scope.end)
        assert c.execute("SELECT * FROM herman.item_alias_periods").fetchall() == []
    with pytest.raises(AccessDenied):
        Catalog(b["service"]).propose_item(b["viewer"], b["business"], "forbidden",
            ItemProposal(id=uuid4(), item_id=item.id, predecessor_id=item.id, sku="DENIED",
                         name_fa="ممنوع", evidence=dict(document_id=document, locator="1")))


def test_label_model_rejects_naive_duplicate_and_invented_approval():
    business, item = uuid4(), uuid4()
    now = datetime.now(timezone.utc)
    label = ItemLabel(definition_id=item, business_id=business, item_id=item,
                      sku="SKU", name_fa="نام", decision="baseline")
    for changes in (dict(evidence=dict(document_id=uuid4(), locator="1")), dict(approved_at=now),
                    dict(valid_from=now), dict(decision="approved")):
        with pytest.raises(ValidationError):
            ItemLabel.model_validate(dict(label.model_dump(), **changes))
    with pytest.raises(ValidationError):
        ItemLabelState(business_id=business, effective_at=now.replace(tzinfo=None), labels=[])
    with pytest.raises(ValidationError):
        ItemLabelState(business_id=business, effective_at=now, labels=[label, label])


def test_analysis_rejects_metadata_mismatches_before_writes(current_labels, monkeypatch):
    b, value, _, _ = current_labels
    select = service.select_inputs

    def inconsistent(*args, **kwargs):
        selected = select(*args, **kwargs)
        selected["item_labels"]["labels"][0]["sku"] = "FORGED"
        return selected

    monkeypatch.setattr(service, "select_inputs", inconsistent)
    with pytest.raises(ValueError, match="همخوانی"):
        analyze(b, value, "invalid-metadata")
    with b["db"].transaction(b["viewer"], b["business"]) as c:
        assert not c.execute("SELECT 1 FROM herman.analysis_runs").fetchone()
        assert not c.execute("SELECT 1 FROM herman.idempotency_keys WHERE key='invalid-metadata'").fetchone()
