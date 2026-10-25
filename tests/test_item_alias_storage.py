"""Restricted-database invariants for immutable labels and derived alias periods."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.types.json import Jsonb
from test_backend import backend as backend_fixture
from test_backend import database as database_fixture
from test_tabular_imports import setup_import

from src.backend.catalog import Catalog, ItemDecision
from src.backend.database import migrate
from src.backend.inventory import Item, Movement
from src.backend.service import Conflict, Warehouse, insert

backend = backend_fixture
database = database_fixture


@pytest.fixture
def labels(backend):
    b = backend
    item = Item(id=uuid4(), business_id=b["business"], sku="ORIGINAL", name_fa="نام اصلی", base_unit="each")
    b["service"].catalog(b["editor"], b["business"], "item", item)
    document = b["service"].document(b["owner"], b["business"], "document", "label.txt", "text/plain", b"label")
    return b, item, document


def propose(b, item, document, sku="NEW", predecessor=None, actor="editor"):
    identity = uuid4()
    with b["db"].transaction(b[actor], b["business"], write=True) as c:
        insert(c, "item_definitions", dict(business_id=b["business"], id=identity, item_id=item.id,
            predecessor_id=predecessor or item.id, sku=sku, name_fa="نام بررسی‌شده", document_id=document,
            locator="line:1", created_by=b[actor]))
    return identity


def review(b, identity, *, when=None, approved=True, actor="owner"):
    with b["db"].transaction(b[actor], b["business"]) as c:
        insert(c, "item_decisions", dict(business_id=b["business"], definition_id=identity,
            actor_id=b[actor], approved=approved, reason_fa="بررسی شد", effective_at=when))


def aliases(b):
    with b["db"].transaction(b["owner"], b["business"]) as c:
        return c.execute("SELECT * FROM herman.item_alias_periods ORDER BY definition_id").fetchall()


def at(b, sku, when):
    with b["db"].transaction(b["owner"], b["business"]) as c:
        return c.execute("SELECT definition_id,item_id FROM herman.item_alias_periods "
            "WHERE business_id=%s AND sku=%s AND validity @> %s::timestamptz",
            (b["business"], sku, when)).fetchall()


def test_baseline_editor_capture_and_reentry_preserve_original(labels):
    b, item, _ = labels
    before = aliases(b)
    assert len(before) == 1 and before[0]["definition_id"] == item.id
    assert before[0]["validity"].lower is None and before[0]["validity"].upper is None
    with b["db"].transaction(b["viewer"], b["business"]) as c:
        original = c.execute("SELECT * FROM herman.item_definitions WHERE id=%s", (item.id,)).fetchone()
    assert original["baseline"] and original["created_by"] is None
    assert original["document_id"] is None and original["predecessor_id"] is None
    assert original["sku"] == item.sku and original["name_fa"] == item.name_fa
    migrate(b["admin"])
    assert aliases(b) == before


def test_future_revision_boundary_rejection_and_original_immutability(labels):
    b, item, document = labels
    rejected = propose(b, item, document)
    review(b, rejected, approved=False)
    assert len(aliases(b)) == 1
    identity = propose(b, item, document)
    when = datetime.now(timezone.utc) + timedelta(days=1)
    review(b, identity, when=when)
    assert at(b, "ORIGINAL", when-timedelta(microseconds=1)) == [dict(definition_id=item.id, item_id=item.id)]
    assert at(b, "ORIGINAL", when) == []
    assert at(b, "NEW", when) == [dict(definition_id=identity, item_id=item.id)]
    with b["db"].transaction(b["owner"], b["business"]) as c:
        assert c.execute("SELECT sku,name_fa FROM herman.items WHERE id=%s", (item.id,)).fetchone() == {
            "sku": item.sku, "name_fa": item.name_fa}
    with pytest.raises(psycopg.errors.CheckViolation):
        propose(b, item, document, predecessor=item.id)


def test_backdating_and_future_chain_order_are_rejected(labels):
    b, item, document = labels
    identity = propose(b, item, document)
    with pytest.raises(psycopg.errors.CheckViolation):
        review(b, identity, when=datetime.now(timezone.utc)-timedelta(days=1))
    when = datetime.now(timezone.utc)+timedelta(days=2)
    review(b, identity, when=when)
    successor = propose(b, item, document, sku="LAST", predecessor=identity)
    with pytest.raises(psycopg.errors.CheckViolation):
        review(b, successor, when=when)
    review(b, successor, when=when+timedelta(days=1))
    assert at(b, "NEW", when) == [dict(definition_id=identity, item_id=item.id)]
    assert at(b, "LAST", when+timedelta(days=1)) == [dict(definition_id=successor, item_id=item.id)]


def test_alias_reuse_requires_nonoverlapping_reviewed_interval(labels):
    b, item, document = labels
    other = Item(id=uuid4(), business_id=b["business"], sku="OTHER", name_fa="دیگر", base_unit="each")
    b["service"].catalog(b["owner"], b["business"], "other", other)
    transfer = propose(b, other, document, sku=item.sku)
    when = datetime.now(timezone.utc)+timedelta(days=1)
    with pytest.raises(psycopg.errors.ExclusionViolation):
        review(b, transfer, when=when)
    renamed = propose(b, item, document, sku="RENAMED")
    review(b, renamed, when=when)
    review(b, transfer, when=when)
    assert at(b, item.sku, when) == [dict(definition_id=transfer, item_id=other.id)]
    assert at(b, item.sku, when-timedelta(microseconds=1)) == [dict(definition_id=item.id, item_id=item.id)]


def test_concurrent_items_cannot_claim_overlapping_alias(labels):
    b, item, document = labels
    other = Item(id=uuid4(), business_id=b["business"], sku="OTHER", name_fa="دیگر", base_unit="each")
    b["service"].catalog(b["owner"], b["business"], "other", other)
    proposals = [propose(b, target, document, sku="SHARED") for target in (item, other)]
    when = datetime.now(timezone.utc)+timedelta(days=1)

    def attempt(identity):
        try:
            review(b, identity, when=when)
            return "approved"
        except (psycopg.errors.ExclusionViolation, psycopg.errors.DeadlockDetected):
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(attempt, proposals)) == ["approved", "conflict"]
    assert len(at(b, "SHARED", when)) == 1
    with b["db"].transaction(b["owner"], b["business"]) as c:
        assert c.execute("SELECT count(*) AS n FROM herman.item_decisions WHERE approved").fetchone()["n"] == 1


def test_service_concurrent_alias_reviews_commit_one_decision(labels):
    b, item, document = labels
    other = Item(id=uuid4(), business_id=b["business"], sku="OTHER", name_fa="دیگر", base_unit="each")
    b["service"].catalog(b["owner"], b["business"], "other", other)
    proposals = [propose(b, target, document, sku="SHARED") for target in (item, other)]
    value = ItemDecision(approved=True, reason_fa="بررسی شد",
                         effective_at=datetime.now(timezone.utc)+timedelta(days=1))
    catalog = Catalog(b["service"])

    def attempt(identity):
        try:
            catalog.decide_item(b["owner"], b["business"], str(identity), identity, value)
            return "approved"
        except (psycopg.errors.ExclusionViolation, Conflict):
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(attempt, proposals)) == ["approved", "conflict"]
    assert len(at(b, "SHARED", value.effective_at)) == 1
    with b["db"].transaction(b["owner"], b["business"]) as c:
        assert c.execute("SELECT count(*) AS n FROM herman.item_decisions WHERE approved").fetchone()["n"] == 1
        assert c.execute("SELECT count(*) AS n FROM herman.audit_events WHERE action='item.reviewed'").fetchone()["n"] == 1


@pytest.mark.parametrize("failures", [1, 3])
def test_deadlock_retry_rolls_back_data_keys_and_audit(backend, monkeypatch, failures):
    b = backend
    service = b["service"]
    original = service._audit
    calls = []

    def interrupted(*args):
        calls.append(True)
        if len(calls) <= failures:
            raise psycopg.errors.DeadlockDetected("private transaction details")
        return original(*args)

    value = Warehouse(id=uuid4(), business_id=b["business"], name="انبار آزمون")
    with monkeypatch.context() as patch:
        patch.setattr(service, "_audit", interrupted)
        if failures == 3:
            with pytest.raises(Conflict, match="تعارض"):
                service.catalog(b["owner"], b["business"], "deadlock", value)
            assert len(calls) == 3
            with b["db"].transaction(b["owner"], b["business"]) as c:
                assert c.execute("SELECT 1 FROM herman.warehouses WHERE id=%s", (value.id,)).fetchone() is None
                assert c.execute("SELECT 1 FROM herman.idempotency_keys WHERE key='deadlock'").fetchone() is None
        else:
            assert service.catalog(b["owner"], b["business"], "deadlock", value) == value.id
            assert len(calls) == 2
    assert service.catalog(b["owner"], b["business"], "deadlock", value) == value.id
    with b["db"].transaction(b["owner"], b["business"]) as c:
        assert c.execute("SELECT count(*) AS n FROM herman.warehouses WHERE id=%s", (value.id,)).fetchone()["n"] == 1
        assert c.execute("SELECT count(*) AS n FROM herman.audit_events WHERE entity_id=%s", (value.id,)).fetchone()["n"] == 1


def test_raw_role_tenant_and_projection_guards(labels):
    b, item, document = labels
    identity = propose(b, item, document)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        review(b, identity, actor="editor")
    with b["db"].transaction(b["stranger"], b["other"]) as c:
        assert c.execute("SELECT * FROM herman.item_definitions").fetchall() == []
        assert c.execute("SELECT * FROM herman.item_alias_periods").fetchall() == []
    for statement in [
        "UPDATE herman.item_alias_periods SET sku='forged'",
        "DELETE FROM herman.item_alias_periods",
        "INSERT INTO herman.item_alias_periods SELECT * FROM herman.item_alias_periods",
        "UPDATE herman.item_definitions SET name_fa='forged'",
        "DELETE FROM herman.item_decisions",
        "SELECT herman.item_publish_alias()",
    ]:
        with pytest.raises(psycopg.errors.InsufficientPrivilege), b["db"].transaction(b["owner"], b["business"]) as c:
            c.execute(statement)
    with pytest.raises(psycopg.errors.CheckViolation), b["db"].transaction(b["owner"], b["business"]) as c:
        insert(c, "item_definitions", dict(business_id=b["business"], id=uuid4(), item_id=item.id,
            baseline=True, sku=item.sku, name_fa=item.name_fa))


@pytest.mark.parametrize("mismatch", ["item", "time"])
def test_source_definition_must_match_record_item_and_event_time(backend, mismatch):
    b = backend
    _, mapping = setup_import(b)
    with b["db"].transaction(b["owner"], b["business"]) as c:
        item_id = c.execute("SELECT id FROM herman.items WHERE sku='MEAT'").fetchone()["id"]
        extraction = c.execute("SELECT j.document_id FROM herman.extractions e "
            "JOIN herman.extraction_jobs j ON (j.business_id,j.id)=(e.business_id,e.job_id) "
            "WHERE e.id=%s", (mapping.extraction_id,)).fetchone()
    event_time = datetime.now(timezone.utc)+timedelta(days=2)
    if mismatch == "item":
        item = Item(id=uuid4(), business_id=b["business"], sku="OTHER", name_fa="دیگر", base_unit="each")
        b["service"].catalog(b["owner"], b["business"], "other", item)
        captured = item.id
    else:
        item = Item(id=item_id, business_id=b["business"], sku="MEAT", name_fa="گوشت", base_unit="g")
        identity = propose(b, item, extraction["document_id"], sku="RENAMED")
        review(b, identity, when=event_time-timedelta(days=1))
        captured = item.id
    record = Movement(id=uuid4(), business_id=b["business"], warehouse_id=mapping.warehouse_id,
        item_id=item_id, occurred_at=event_time, quantity="1", unit="g", kind="purchase",
        evidence=dict(document_id=extraction["document_id"], locator="CSV:row:2"))
    with pytest.raises(psycopg.errors.CheckViolation, match="source item definition"), b["db"].transaction(
        b["owner"], b["business"], write=True
    ) as c:
        batch = uuid4()
        insert(c, "import_batches", dict(business_id=b["business"], id=batch,
            extraction_id=mapping.extraction_id, created_by=b["owner"], mapping=Jsonb({})))
        b["service"]._insert_proposal(c, b["owner"], b["business"], record)
        insert(c, "record_sources", dict(business_id=b["business"], id=record.id, batch_id=batch,
            extraction_id=mapping.extraction_id, document_id=extraction["document_id"], sheet="CSV",
            source_row=2, record_kind="movement", source_values=Jsonb({}), created_by=b["owner"],
            item_definition_id=captured))


def test_legacy_item_migration_preserves_values_without_invented_evidence(database):
    _, admin = database
    name = "herman_migration_test_"+uuid4().hex
    dsn = make_conninfo(admin, dbname=name)
    root = Path(__file__).parents[1]/"src"/"backend"
    with psycopg.connect(admin, autocommit=True) as c:
        c.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        business, actor, item = [uuid4() for _ in range(3)]
        with psycopg.connect(dsn) as c:
            c.execute((root/"schema.sql").read_text(encoding="utf-8-sig"))
            for version in range(2, 17):
                c.execute((root/f"migration_{version:03}.sql").read_text(encoding="utf-8-sig"))
            insert(c, "users", dict(id=actor, display_name="test"))
            insert(c, "businesses", dict(id=business, name="test", industry="retail", created_by=actor))
            insert(c, "items", dict(business_id=business, id=item, sku="OLD", name_fa="قدیمی",
                base_unit="each", consumption_mode="direct"))
            original = c.execute("SELECT * FROM herman.items").fetchall()
        migrate(dsn)
        migrate(dsn)
        with psycopg.connect(dsn) as c:
            assert c.execute("SELECT * FROM herman.items").fetchall() == original
            assert c.execute("SELECT id,item_id,sku,name_fa,baseline,document_id,created_by "
                "FROM herman.item_definitions").fetchall() == [(item,item,"OLD","قدیمی",True,None,None)]
            assert c.execute("SELECT count(*) FROM herman.item_decisions").fetchone()[0] == 0
    finally:
        with psycopg.connect(admin, autocommit=True) as c:
            c.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
