"""Database invariants for reviewed prospective pack definitions."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo
from test_backend import backend as backend_fixture
from test_backend import database as database_fixture

from src.backend.catalog import Catalog, PackDecision, PackProposal, pack_timeline
from src.backend.database import AccessDenied, migrate
from src.backend.inventory import Item, UnitConversion
from src.backend.service import Conflict, insert

backend = backend_fixture
database = database_fixture


@pytest.fixture
def catalog(backend):
    b = backend
    service = b["service"]
    item = Item(id=uuid4(), business_id=b["business"], sku="PACK", name_fa="بسته", base_unit="each")
    service.catalog(b["owner"], b["business"], "item", item)
    document = service.document(b["owner"], b["business"], "document", "pack.txt", "text/plain", b"8 units")
    factor = UnitConversion(id=uuid4(), business_id=b["business"], item_id=item.id,
                            base_quantity="8", evidence=dict(document_id=document, locator="line:1"))
    service.catalog(b["owner"], b["business"], "factor", factor)
    return b, Catalog(service), item, factor


def proposal(factor, **changes):
    return PackProposal.model_validate(dict(id=uuid4(), item_id=factor.item_id,
        predecessor_id=factor.id, base_quantity="10", evidence=factor.evidence, **changes))


def approve(b, catalog, identity, *, key="approve", when=None, approved=True):
    return catalog.decide_pack(b["owner"], b["business"], key, identity,
        PackDecision(approved=approved, reason_fa="با سند بررسی شد", effective_at=when))


def timeline(b, item):
    with b["db"].transaction(b["owner"], b["business"]) as c:
        return pack_timeline(c, b["business"], item.id)


def test_baseline_capture_migration_reentry_and_immutable_source(catalog):
    b, cat, item, factor = catalog
    original = timeline(b, item)
    assert len(original) == 1
    assert original[0].id == factor.id
    assert original[0].decision == "baseline"
    assert original[0].approved_at is None and original[0].valid_from is None
    assert original[0].base_quantity == 8
    migrate(b["admin"])
    assert timeline(b, item) == original
    row = cat.pack_history(b["viewer"], b["business"], item.id)[0]
    assert row["created_by"] is None and row["approved"] is None
    with pytest.raises(psycopg.errors.CheckViolation), b["db"].transaction(b["owner"], b["business"]) as c:
        insert(c, "pack_definitions", dict(business_id=b["business"], id=uuid4(), item_id=item.id,
            baseline=True, base_quantity=99, document_id=factor.evidence.document_id, locator="forged"))


def test_proposal_review_timeline_and_idempotency(catalog):
    b, cat, item, factor = catalog
    value = proposal(factor)
    identity = cat.propose_pack(b["editor"], b["business"], "proposal", value)
    assert cat.propose_pack(b["editor"], b["business"], "proposal", value) == identity
    assert len(timeline(b, item)) == 1
    activation = datetime.now(timezone.utc) + timedelta(days=1)
    approve(b, cat, identity, when=activation)
    assert approve(b, cat, identity, when=activation) == identity
    versions = timeline(b, item)
    assert [r.base_quantity for r in versions] == [8, 10]
    assert versions[0].valid_to == activation == versions[1].valid_from
    assert versions[1].approved_at <= activation
    with b["db"].transaction(b["owner"], b["business"]) as c:
        assert c.execute("SELECT base_quantity FROM herman.unit_conversions WHERE business_id=%s AND id=%s",
                         (b["business"], factor.id)).fetchone()["base_quantity"] == 8
        assert c.execute("SELECT count(*) AS n FROM herman.audit_events WHERE business_id=%s "
                         "AND action IN ('pack.proposed','pack.reviewed')", (b["business"],)).fetchone()["n"] == 2
    with pytest.raises(Conflict):
        cat.propose_pack(b["editor"], b["business"], "proposal",
                         value.model_copy(update={"base_quantity": Decimal(11)}))


def test_rejection_and_competing_approvals(catalog):
    b, cat, item, factor = catalog
    values = [proposal(factor) for _ in range(3)]
    for index, value in enumerate(values):
        cat.propose_pack(b["editor"], b["business"], f"p{index}", value)
    approve(b, cat, values[0].id, approved=False)
    assert len(timeline(b, item)) == 1

    def attempt(index):
        try:
            approve(b, cat, values[index].id, key=f"a{index}")
            return "approved"
        except psycopg.errors.UniqueViolation:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(attempt, (1, 2)))
    assert sorted(outcomes) == ["approved", "conflict"]
    assert len(timeline(b, item)) == 2
    with pytest.raises(psycopg.errors.CheckViolation):
        cat.propose_pack(b["editor"], b["business"], "stale", proposal(factor))


def test_no_backdating_or_reversed_future_chain(catalog):
    b, cat, item, factor = catalog
    value = proposal(factor)
    cat.propose_pack(b["editor"], b["business"], "p", value)
    with pytest.raises(psycopg.errors.CheckViolation):
        approve(b, cat, value.id, when=datetime.now(timezone.utc)-timedelta(days=1))
    future = datetime.now(timezone.utc)+timedelta(days=2)
    approve(b, cat, value.id, when=future)
    successor = proposal(factor).model_copy(update={"predecessor_id": value.id})
    cat.propose_pack(b["editor"], b["business"], "p2", successor)
    with pytest.raises(psycopg.errors.CheckViolation):
        approve(b, cat, successor.id, key="a2", when=future)
    approve(b, cat, successor.id, key="a2", when=future+timedelta(days=1))
    assert len(timeline(b, item)) == 3


@pytest.mark.parametrize("actor", ["viewer", "stranger"])
def test_unauthorized_proposal(catalog, actor):
    b, cat, _, factor = catalog
    with pytest.raises(AccessDenied):
        cat.propose_pack(b[actor], b["business"], "p", proposal(factor))


def test_review_role_and_direct_database_guards(catalog):
    b, cat, item, factor = catalog
    value = proposal(factor)
    cat.propose_pack(b["editor"], b["business"], "p", value)
    with pytest.raises(AccessDenied):
        cat.decide_pack(b["editor"], b["business"], "a", value.id,
                       PackDecision(approved=True, reason_fa="بررسی"))
    with pytest.raises(psycopg.errors.InsufficientPrivilege), b["db"].transaction(b["editor"], b["business"]) as c:
        insert(c, "pack_decisions", dict(business_id=b["business"], definition_id=value.id,
            approved=True, actor_id=b["owner"], reason_fa="forged"))
    for actor in (b["stranger"],):
        with b["db"].transaction(actor, b["other"]) as c:
            assert c.execute("SELECT * FROM herman.pack_definitions WHERE business_id=%s",
                             (b["business"],)).fetchall() == []
    with pytest.raises(psycopg.errors.InsufficientPrivilege), psycopg.connect(b["admin"]) as c:
        c.execute("UPDATE herman.pack_definitions SET base_quantity=99 WHERE business_id=%s AND id=%s",
                  (b["business"], value.id))
    approve(b, cat, value.id)
    with pytest.raises(psycopg.errors.InsufficientPrivilege), psycopg.connect(b["admin"]) as c:
        c.execute("DELETE FROM herman.pack_decisions WHERE business_id=%s AND definition_id=%s",
                  (b["business"], value.id))


def test_source_tampering_blocks_approval(catalog):
    b, cat, _, factor = catalog
    value = proposal(factor)
    cat.propose_pack(b["editor"], b["business"], "p", value)
    row, _ = b["service"].read_document(b["owner"], b["business"], factor.evidence.document_id)
    (b["blob_root"]/str(b["business"])/row["sha256"]).write_bytes(b"tampered")
    with pytest.raises(Conflict):
        approve(b, cat, value.id)
    with pytest.raises(Conflict):
        cat.propose_pack(b["editor"], b["business"], "p2", proposal(factor))
    approve(b, cat, value.id, approved=False)


def test_upgrade_copies_legacy_conversion_without_fabricated_approval(database):
    _, admin = database
    name = "herman_migration_test_" + uuid4().hex
    dsn = make_conninfo(admin, dbname=name)
    root = Path(__file__).parents[1]/"src"/"backend"
    with psycopg.connect(admin, autocommit=True) as c:
        c.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        business, actor, item, document, conversion = [uuid4() for _ in range(5)]
        with psycopg.connect(dsn) as c:
            c.execute((root/"schema.sql").read_text(encoding="utf-8-sig"))
            for version in range(2, 15):
                c.execute((root/f"migration_{version:03}.sql").read_text(encoding="utf-8-sig"))
            insert(c, "users", dict(id=actor, display_name="test"))
            insert(c, "businesses", dict(id=business, name="test", industry="retail", created_by=actor))
            insert(c, "documents", dict(business_id=business, id=document, sha256="0"*64,
                original_name="legacy.txt", media_type="text/plain", byte_size=0, created_by=actor))
            insert(c, "items", dict(business_id=business, id=item, sku="OLD", name_fa="قدیمی",
                base_unit="each", consumption_mode="direct"))
            insert(c, "unit_conversions", dict(business_id=business, id=conversion, item_id=item,
                unit="pack", base_quantity=Decimal("8.123456"), document_id=document, locator="line:1"))
            original = c.execute("SELECT * FROM herman.unit_conversions").fetchall()
        migrate(dsn)
        migrate(dsn)
        with psycopg.connect(dsn) as c:
            assert c.execute("SELECT * FROM herman.unit_conversions").fetchall() == original
            assert c.execute("SELECT id,item_id,base_quantity,document_id,locator,baseline,created_by "
                "FROM herman.pack_definitions").fetchall() == [
                    (conversion, item, Decimal("8.123456"), document, "line:1", True, None)]
            assert c.execute("SELECT count(*) FROM herman.pack_decisions").fetchone()[0] == 0
    finally:
        with psycopg.connect(admin, autocommit=True) as c:
            c.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))
