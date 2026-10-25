"""Historical pack metadata invariants against real PostgreSQL."""

import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import monotonic, sleep
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.types.json import Jsonb
from test_backend import backend as backend_fixture
from test_backend import database as database_fixture

from src.backend.database import migrate
from src.backend.inventory import Count, Fulfillment, Item, Movement, Recipe, UnitConversion
from src.backend.service import Warehouse, canonical, insert

backend = backend_fixture
database = database_fixture


@pytest.fixture
def context(backend):
    b = backend
    service = b["service"]
    item = Item(id=uuid4(), business_id=b["business"], sku="PACK", name_fa="کالا", base_unit="each")
    warehouse = Warehouse(id=uuid4(), business_id=b["business"], name="انبار")
    service.catalog(b["owner"], b["business"], "item", item)
    service.catalog(b["owner"], b["business"], "warehouse", warehouse)
    document = service.document(b["owner"], b["business"], "document", "pack.txt", "text/plain", b"8 units")
    return b, item, warehouse, dict(document_id=document, locator="line:1")


def factor(context):
    b, item, _, evidence = context
    value = UnitConversion(id=uuid4(), business_id=b["business"], item_id=item.id,
                           base_quantity="8", evidence=evidence)
    b["service"].catalog(b["owner"], b["business"], str(value.id), value)
    return value


def direct(context, kind=Count, when=None):
    b, item, warehouse, evidence = context
    fields = dict(id=uuid4(), business_id=b["business"], warehouse_id=warehouse.id,
                  occurred_at=when or datetime.now(timezone.utc), quantity="1", unit="pack", evidence=evidence)
    fields["product_id" if kind is Fulfillment else "item_id"] = item.id
    if kind is Movement:
        fields["kind"] = "purchase"
    value = kind(**fields)
    b["service"].propose(b["editor"], b["business"], str(value.id), value)
    return value


def check(context, record):
    b = context[0]
    with b["db"].transaction(b["viewer"], b["business"]) as c:
        return c.execute("SELECT * FROM herman.pack_binding_checks WHERE record_id=%s", (record.id,)).fetchone()


def review(context, target, definition, approved=True, actor=None):
    b, _, _, evidence = context
    with b["db"].transaction(actor or b["owner"], b["business"], snapshot=False) as c:
        identity = uuid4()
        insert(c, "pack_binding_reviews", dict(business_id=b["business"], id=identity,
            check_id=target["id"], approved=approved, definition_id=definition,
            actor_id=actor or b["owner"], reason_fa="با سند بررسی شد", **evidence))
        return identity


@pytest.mark.parametrize("kind", [Count, Movement, Fulfillment])
def test_native_capture_known_before_and_future_deferred(context, kind):
    b = context[0]
    version = factor(context)
    record = direct(context, kind)
    captured = check(context, record)
    assert captured["state"] == "bound" and captured["definition_id"] == version.id
    assert captured["origin"] == "known_before_event" and captured["created_by"] == b["editor"]
    assert captured["item_id"] == context[1].id and captured["occurred_at"] == record.occurred_at
    assert captured["fulfillment_id"] == (record.id if kind is Fulfillment else None)
    future = direct(context, kind, datetime.now(timezone.utc)+timedelta(days=1))
    assert check(context, future) is None
    with b["db"].transaction(b["owner"], b["business"]) as c:
        row = c.execute("SELECT * FROM herman.pack_definition_observations WHERE definition_id=%s",
                        (version.id,)).fetchone()
        assert row["origin"] == "native_capture" and row["observed_at"] <= record.occurred_at
        assert c.execute("SELECT pack_binding_legacy FROM herman.records WHERE id=%s",
                         (record.id,)).fetchone()["pack_binding_legacy"] is False
    with pytest.raises(psycopg.errors.CheckViolation), b["db"].transaction(b["owner"], b["business"]) as c:
        insert(c, "pack_binding_checks", dict(business_id=b["business"], id=uuid4(), record_id=future.id,
            fulfillment_id=future.id if kind is Fulfillment else None))


def test_late_baseline_never_rewrites_check_and_review_slot_is_atomic(context):
    b = context[0]
    old = direct(context, when=datetime.now(timezone.utc)-timedelta(days=1))
    original = check(context, old)
    assert original["state"] == "unresolved" and original["missing_reason"] == "missing_definition"
    version = factor(context)
    assert check(context, old) == original
    other = direct(context, when=old.occurred_at)
    assert check(context, other)["missing_reason"] == "baseline_not_known_before_event"
    review(context, original, None, approved=False)

    def attempt(_):
        try:
            review(context, original, version.id)
            return True
        except psycopg.errors.UniqueViolation:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(attempt, range(2))) == [False, True]
    assert check(context, old) == original
    with b["db"].transaction(b["owner"], b["business"]) as c:
        rows = c.execute("SELECT approved FROM herman.pack_binding_reviews WHERE check_id=%s",
                         (original["id"],)).fetchall()
        assert sorted(r["approved"] for r in rows) == [False, True]


def test_scope_privileges_observation_and_derived_fields(context):
    b = context[0]
    version = factor(context)
    old = direct(context, when=datetime.now(timezone.utc)-timedelta(days=1))
    target = check(context, old)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        review(context, target, version.id, actor=b["editor"])
    with b["db"].transaction(b["stranger"], b["other"]) as c:
        assert c.execute("SELECT * FROM herman.pack_binding_checks").fetchall() == []
        assert c.execute("SELECT * FROM herman.pack_definition_observations").fetchall() == []
    for table in ("pack_definition_observations", "pack_binding_cutover", "pack_binding_checks", "pack_binding_reviews"):
        with pytest.raises(psycopg.errors.InsufficientPrivilege), b["db"].transaction(b["owner"], b["business"]) as c:
            c.execute(sql.SQL("UPDATE herman.{} SET {}={}").format(sql.Identifier(table),
                sql.Identifier("singleton" if table == "pack_binding_cutover" else "business_id"),
                sql.Identifier("singleton" if table == "pack_binding_cutover" else "business_id")))
    with pytest.raises(psycopg.errors.InsufficientPrivilege), b["db"].transaction(b["owner"], b["business"]) as c:
        insert(c, "pack_definition_observations", dict(business_id=b["business"], definition_id=version.id,
            observed_at=datetime.now(timezone.utc)-timedelta(days=100), origin="migration_observation"))
    # Remove the unique-key conflict by testing a new recipe-use context.
    recipe, fulfillment = recipe_context(context)
    with b["db"].transaction(b["editor"], b["business"]) as c:
        identity = uuid4()
        insert(c, "pack_binding_checks", dict(business_id=b["business"], id=identity, record_id=recipe.id,
            ingredient_id=context[1].id, fulfillment_id=fulfillment.id, recipe_path=[recipe.id],
            item_id=uuid4(), occurred_at=datetime.now(timezone.utc)+timedelta(days=3),
            definition_id=version.id, state="bound", origin="migration_derived", missing_reason=None,
            created_by=b["stranger"], captured_at=datetime(2000, 1, 1, tzinfo=timezone.utc)))
        captured = c.execute("SELECT * FROM herman.pack_binding_checks WHERE id=%s", (identity,)).fetchone()
        assert captured["origin"] == "known_before_event" and captured["item_id"] == context[1].id
        assert captured["occurred_at"] == fulfillment.occurred_at and captured["created_by"] == b["editor"]
        assert captured["captured_at"].year > 2000


def recipe_context(context):
    b, item, warehouse, evidence = context
    product = Item(id=uuid4(), business_id=b["business"], sku=str(uuid4()), name_fa="محصول",
                   base_unit="each", consumption_mode="recipe")
    b["service"].catalog(b["owner"], b["business"], str(product.id), product)
    now = datetime.now(timezone.utc)
    recipe = Recipe(id=uuid4(), business_id=b["business"], product_id=product.id,
        valid_from=now-timedelta(days=2), output_quantity="1", output_unit="each", evidence=evidence,
        lines=[dict(item_id=item.id, quantity="1", unit="pack")])
    fulfillment = Fulfillment(id=uuid4(), business_id=b["business"], warehouse_id=warehouse.id,
        product_id=product.id, occurred_at=now, quantity="1", unit="each", evidence=evidence)
    for value in (recipe, fulfillment):
        b["service"].propose(b["editor"], b["business"], str(value.id), value)
    return recipe, fulfillment


def test_recipe_topology_unit_kind_and_time_validation(context):
    b = context[0]
    factor(context)
    recipe, fulfillment = recipe_context(context)
    for changes in (dict(recipe_path=[]), dict(recipe_path=[recipe.id, recipe.id]),
                    dict(recipe_path=[uuid4(), recipe.id]), dict(ingredient_id=None),
                    dict(fulfillment_id=uuid4()), dict(record_id=fulfillment.id)):
        fields = dict(business_id=b["business"], id=uuid4(), record_id=recipe.id,
                      ingredient_id=context[1].id, fulfillment_id=fulfillment.id, recipe_path=[recipe.id])
        fields.update(changes)
        with pytest.raises(psycopg.errors.CheckViolation), b["db"].transaction(b["owner"], b["business"]) as c:
            insert(c, "pack_binding_checks", fields)
    with b["db"].transaction(b["owner"], b["business"]) as c:
        insert(c, "pack_binding_checks", dict(business_id=b["business"], id=uuid4(), record_id=recipe.id,
            ingredient_id=context[1].id, fulfillment_id=fulfillment.id, recipe_path=[recipe.id]))
    # PostgreSQL array equality includes bounds: reject a second encoding of the same usage key.
    for lower_bound in (0, 2):
        shifted_path = f"[{lower_bound}:{lower_bound}]={{{recipe.id}}}"
        with pytest.raises(psycopg.errors.CheckViolation), b["db"].transaction(b["owner"], b["business"]) as c:
            c.execute("INSERT INTO herman.pack_binding_checks"
                "(business_id,id,record_id,ingredient_id,fulfillment_id,recipe_path) "
                "VALUES(%s,%s,%s,%s,%s,%s::uuid[])",
                (b["business"], uuid4(), recipe.id, context[1].id, fulfillment.id, shifted_path))


def test_pre18_upgrade_backfill_and_reentry_preserve_original_values(database):
    _, admin = database
    name = "binding_upgrade_" + uuid4().hex
    dsn = make_conninfo(admin, dbname=name)
    root = Path(__file__).parents[1]/"src"/"backend"
    with psycopg.connect(admin, autocommit=True) as c:
        c.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        business, actor, item, warehouse, document, conversion, record, future = [uuid4() for _ in range(8)]
        now = datetime.now(timezone.utc)
        with psycopg.connect(dsn) as c:
            c.execute((root/"schema.sql").read_text(encoding="utf-8-sig"))
            for version in range(2, 15):
                c.execute((root/f"migration_{version:03}.sql").read_text(encoding="utf-8-sig"))
            insert(c, "users", dict(id=actor, display_name="test"))
            insert(c, "businesses", dict(id=business, name="test", industry="retail", created_by=actor))
            insert(c, "memberships", dict(business_id=business, user_id=actor, role="owner"))
            insert(c, "documents", dict(business_id=business, id=document, sha256="0"*64,
                original_name="legacy.txt", media_type="text/plain", byte_size=0, created_by=actor))
            insert(c, "warehouses", dict(business_id=business, id=warehouse, name="test"))
            insert(c, "items", dict(business_id=business, id=item, sku="OLD", name_fa="قدیمی",
                base_unit="each", consumption_mode="direct"))
            insert(c, "unit_conversions", dict(business_id=business, id=conversion, item_id=item,
                unit="pack", base_quantity="8.123456", document_id=document, locator="line:1"))
            for identity, when in ((record, now-timedelta(days=1)), (future, now+timedelta(days=1))):
                insert(c, "records", dict(business_id=business, id=identity, kind="count",
                    document_id=document, locator="line:1", created_by=actor))
                insert(c, "stock_counts", dict(business_id=business, id=identity, warehouse_id=warehouse,
                    item_id=item, occurred_at=when, quantity=1, unit="pack"))
            for version in range(15, 18):
                c.execute((root/f"migration_{version:03}.sql").read_text(encoding="utf-8-sig"))
            c.execute("SELECT set_config('herman.user_id',%s,true)", (str(actor),))
            c.execute("SELECT set_config('herman.business_id',%s,true)", (str(business),))
            successor, reviewed_record = uuid4(), uuid4()
            insert(c, "pack_definitions", dict(business_id=business, id=successor, item_id=item,
                predecessor_id=conversion, base_quantity="10", document_id=document,
                locator="revision:1", created_by=actor))
            insert(c, "pack_decisions", dict(business_id=business, definition_id=successor,
                predecessor_id=conversion, approved=True, actor_id=actor, reason_fa="بررسی شد"))
            event_time = c.execute("SELECT clock_timestamp()").fetchone()[0]
            insert(c, "records", dict(business_id=business, id=reviewed_record, kind="count",
                document_id=document, locator="reviewed:1", created_by=actor))
            insert(c, "stock_counts", dict(business_id=business, id=reviewed_record, warehouse_id=warehouse,
                item_id=item, occurred_at=event_time, quantity=1, unit="pack"))
            original = c.execute("SELECT * FROM herman.stock_counts ORDER BY id").fetchall()
            # Migration must retain even an unsupported legacy envelope without normalizing it.
            legacy_snapshot = {"contract_version": "legacy.test.v0", "quantity_pack": "8.123456"}
            analysis = uuid4()
            insert(c, "analysis_runs", dict(business_id=business, id=analysis, actor_id=actor,
                input_sha256=hashlib.sha256(canonical(legacy_snapshot).encode()).hexdigest(),
                input_snapshot=Jsonb(legacy_snapshot), result=Jsonb({"status": "unknown", "fixture": True})))
            original_receipt = c.execute("SELECT input_snapshot::text,result::text,input_sha256,pack_uses::text "
                                        "FROM herman.analysis_runs WHERE id=%s", (analysis,)).fetchone()
        # A writer that already holds the source-table lock must finish before cutover capture.
        # Its later event would be excluded if captured_at were stamped before waiting for this lock.
        concurrent_record = uuid4()
        with psycopg.connect(dsn) as writer, ThreadPoolExecutor(max_workers=1) as pool:
            writer.execute("LOCK TABLE herman.records IN ROW EXCLUSIVE MODE")
            upgrading = pool.submit(migrate, dsn)
            deadline = monotonic()+3
            with psycopg.connect(dsn, autocommit=True) as observer:
                while not observer.execute("SELECT EXISTS(SELECT 1 FROM pg_locks "
                    "WHERE relation='herman.records'::regclass AND database="
                    "(SELECT oid FROM pg_database WHERE datname=current_database()) "
                    "AND mode='AccessExclusiveLock' AND NOT granted)").fetchone()[0]:
                    assert monotonic()<deadline, "migration did not reach the source lock barrier"
                    sleep(0.01)
            concurrent_time = writer.execute("SELECT clock_timestamp()").fetchone()[0]
            insert(writer, "records", dict(business_id=business, id=concurrent_record, kind="count",
                document_id=document, locator="concurrent:1", created_by=actor))
            insert(writer, "stock_counts", dict(business_id=business, id=concurrent_record, warehouse_id=warehouse,
                item_id=item, occurred_at=concurrent_time, quantity=1, unit="pack"))
            writer.commit()
            upgrading.result(timeout=30)
        with psycopg.connect(dsn) as c:
            migrated_counts = c.execute("SELECT * FROM herman.stock_counts ORDER BY id").fetchall()
            assert [row for row in migrated_counts if row[1] != concurrent_record] == original
            original = migrated_counts
            saved = c.execute("SELECT * FROM herman.pack_binding_checks").fetchall()
            cutoff = c.execute("SELECT * FROM herman.pack_binding_cutover").fetchone()
            assert set(c.execute("SELECT record_id,definition_id,origin,state,created_by FROM herman.pack_binding_checks"
                                 ).fetchall()) == {
                                     (record, conversion, "migration_derived", "bound", None),
                                     (reviewed_record, successor, "known_before_event", "bound", None),
                                     (concurrent_record, successor, "known_before_event", "bound", None)}
            assert concurrent_time<cutoff[1]
            assert c.execute("SELECT bool_and(pack_binding_legacy) FROM herman.records").fetchone()[0]
            assert c.execute("SELECT observed_at,origin FROM herman.pack_definition_observations WHERE definition_id=%s",
                             (conversion,)).fetchall() == [(cutoff[1], "migration_observation")]
        migrate(dsn)
        with psycopg.connect(dsn) as c:
            assert c.execute("SELECT * FROM herman.pack_binding_checks").fetchall() == saved
            assert c.execute("SELECT * FROM herman.pack_binding_cutover").fetchone() == cutoff
            assert c.execute("SELECT * FROM herman.stock_counts ORDER BY id").fetchall() == original
            assert c.execute("SELECT input_snapshot::text,result::text,input_sha256,pack_uses::text "
                             "FROM herman.analysis_runs WHERE id=%s", (analysis,)).fetchone() == original_receipt
            c.execute("SELECT set_config('herman.user_id',%s,true)", (str(actor),))
            c.execute("SELECT set_config('herman.business_id',%s,true)", (str(business),))
            late = uuid4()
            insert(c, "records", dict(business_id=business, id=late, kind="count", document_id=document,
                locator="late:1", created_by=actor, pack_binding_legacy=True))
            insert(c, "stock_counts", dict(business_id=business, id=late, warehouse_id=warehouse,
                item_id=item, occurred_at=now-timedelta(days=1), quantity=1, unit="pack"))
            assert c.execute("SELECT pack_binding_legacy FROM herman.records WHERE id=%s",
                             (late,)).fetchone() == (False,)
            assert c.execute("SELECT origin,state,missing_reason FROM herman.pack_binding_checks WHERE record_id=%s",
                             (late,)).fetchone() == (
                                 "requires_review", "unresolved", "baseline_not_known_before_event")
    finally:
        with psycopg.connect(admin, autocommit=True) as c:
            c.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))
