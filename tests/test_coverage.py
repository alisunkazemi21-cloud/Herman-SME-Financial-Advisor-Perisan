"""C17 PostgreSQL proofs for bounded, reviewed completeness and immutable history."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import psycopg
import pytest
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from test_backend import backend as backend_fixture
from test_backend import database as database_fixture

from src.backend.coverage import Coverage, CoverageDecision, CoverageProposal
from src.backend.coverage_models import CATEGORIES, CoverageSnapshot
from src.backend.coverage_selection import select_coverage
from src.backend.database import AccessDenied, migrate
from src.backend.inventory import Count, Fulfillment, Item, Movement, Recipe, Scope
from src.backend.inventory import Coverage as Declaration
from src.backend.pack_binding_selection import SelectionLimit
from src.backend.service import Conflict, NotFound, Warehouse, insert

backend = backend_fixture
database = database_fixture


@pytest.fixture
def context(backend):
    b = backend
    svc = b["service"]
    warehouse = Warehouse(id=uuid4(), business_id=b["business"], name="انبار")
    item = Item(id=uuid4(), business_id=b["business"], sku="C17", name_fa="قلم", base_unit="each")
    svc.catalog(b["owner"], b["business"], "warehouse", warehouse)
    svc.catalog(b["owner"], b["business"], "item", item)
    document = svc.document(b["owner"], b["business"], "source", "coverage.txt", "text/plain", b"reviewed counts")
    evidence = dict(document_id=document, locator="line:1")
    scope = Scope(business_id=b["business"], warehouse_id=warehouse.id,
                  start=datetime(2026, 9, 1, tzinfo=timezone.utc), end=datetime(2026, 10, 1, tzinfo=timezone.utc))
    counts = []
    for name, when in (("opening", scope.start), ("closing", scope.end)):
        count = Count(id=uuid4(), business_id=b["business"], warehouse_id=warehouse.id, item_id=item.id,
                      occurred_at=when, quantity="10", unit="each", evidence=evidence)
        svc.propose(b["editor"], b["business"], name, count)
        svc.approve(b["owner"], b["business"], name + "-review", count.id, True, "شمارش بررسی شد")
        counts.append(count)
    return b, Coverage(svc), scope, item, evidence, counts


def proposal(context, **changes):
    _, _, scope, _, evidence, _ = context
    categories = {name: dict(status="records_complete" if name.endswith("count") else
        "not_applicable" if name == "recipes" else "no_events", evidence=evidence, note_fa="با سند بررسی شد")
        for name in CATEGORIES}
    return CoverageProposal.model_validate(dict(id=uuid4(), scope=scope, basis="service", categories=categories,
                                                evidence=evidence, **changes))


def decide(context, value, *, approved=True, key=None):
    b, coverage, *_ = context
    return coverage.decide(b["owner"], b["business"], key or "review-" + str(value.id), value.id,
                           CoverageDecision(approved=approved, reason_fa="شواهد بررسی شد"))


def assess(context):
    b, coverage, scope, *_ = context
    return coverage.assess(b["viewer"], b["business"], scope, "service")


def submit(context, value=None):
    b, coverage, *_ = context
    value = value or proposal(context)
    coverage.propose(b["editor"], b["business"], "proposal-" + str(value.id), value)
    return value


def test_review_required_explicit_no_events_and_roundtrip(context):
    snapshot = assess(context)
    declaration = Declaration(movements_complete=True, fulfillment_complete=True, recipes_complete=True,
                              evidence=context[4])
    assert not snapshot.complete and not snapshot.derive(declaration).movements_complete
    value = submit(context)
    assert not assess(context).complete
    decide(context, value)
    reviewed = assess(context)
    assert reviewed.complete and not reviewed.provisional
    assert reviewed.derive(declaration) == declaration
    assert reviewed.decision.assessment_id == value.id
    assert reviewed.evidence_refs
    assert CoverageSnapshot.model_validate(reviewed.model_dump()) == reviewed
    invalid = reviewed.model_dump()
    invalid["dataset"].pop("unreviewed_count")
    with pytest.raises(ValueError):
        CoverageSnapshot.model_validate(invalid)
    migrate(context[0]["admin"])
    assert assess(context).model_dump(exclude={"as_of"}) == reviewed.model_dump(exclude={"as_of"})
    with pytest.raises(ValueError):
        reviewed.validate_scope(reviewed.scope, "production")


def test_missing_categories_are_reviewable_but_withhold_complete(context):
    value = proposal(context)
    categories = dict(value.categories)
    categories["purchases"] = dict(status="missing", evidence=None, note_fa="سند خرید موجود نیست")
    value = submit(context, CoverageProposal.model_validate(dict(value.model_dump(), categories=categories)))
    decide(context, value)
    assert not assess(context).complete
    assert any("خرید" in reason for reason in assess(context).blockers_fa)
    invalid = value.model_dump()
    invalid["categories"].pop("production")
    with pytest.raises(ValueError):
        CoverageProposal.model_validate(invalid)


def test_pending_required_source_and_no_events_contradiction(context):
    b, _, scope, item, evidence, _ = context
    movement = Movement(id=uuid4(), business_id=b["business"], warehouse_id=scope.warehouse_id,
        item_id=item.id, occurred_at=scope.start + timedelta(days=1), quantity="2", unit="each",
        kind="purchase", evidence=evidence)
    b["service"].propose(b["editor"], b["business"], "purchase", movement)
    value = submit(context)
    decide(context, value)
    pending = assess(context)
    assert not pending.complete and pending.dataset.stats["purchases"].pending_count == 1
    b["service"].approve(b["owner"], b["business"], "purchase-review", movement.id, True, "خرید تأیید شد")
    assert assess(context).dataset.signature != pending.dataset.signature
    replacement = submit(context, proposal(context, supersedes_id=value.id))
    decide(context, replacement)
    contradiction = assess(context)
    assert contradiction.dataset.stats["purchases"].approved_count == 1
    assert not contradiction.complete


def test_pending_unfulfilled_record_still_requires_review(context):
    b, _, scope, item, evidence, _ = context
    event = Fulfillment(id=uuid4(), business_id=b["business"], warehouse_id=scope.warehouse_id,
        product_id=item.id, occurred_at=scope.start + timedelta(days=1), quantity="1", unit="each",
        fulfilled=False, evidence=evidence)
    b["service"].propose(b["editor"], b["business"], "not-fulfilled", event)
    value = submit(context)
    decide(context, value)
    snapshot = assess(context)
    assert snapshot.dataset.stats["sales"].event_count == 0
    assert snapshot.dataset.unreviewed_count == 1 and not snapshot.complete


def test_signature_includes_all_boundary_items_and_approved_corrections(context):
    b, _, scope, item, evidence, counts = context
    value = submit(context)
    decide(context, value)
    original = assess(context)
    replacement = counts[1].model_copy(update={"id": uuid4(), "quantity": Decimal(9)})
    b["service"].correct_inventory(b["editor"], b["business"], "correct", counts[1].id, replacement)
    assert assess(context).dataset.signature == original.dataset.signature
    b["service"].approve(b["owner"], b["business"], "correct-review", replacement.id, True, "اصلاح شمارش")
    corrected = assess(context)
    assert corrected.dataset.signature != original.dataset.signature and not corrected.complete
    second = Item(id=uuid4(), business_id=b["business"], sku="C17-2", name_fa="قلم دوم", base_unit="each")
    b["service"].catalog(b["owner"], b["business"], "second-item", second)
    extra = Count(id=uuid4(), business_id=b["business"], warehouse_id=scope.warehouse_id,
        item_id=second.id, occurred_at=scope.end, quantity="1", unit="each", evidence=evidence)
    b["service"].propose(b["editor"], b["business"], "second-count", extra)
    after = assess(context)
    assert after.dataset.signature != corrected.dataset.signature
    assert after.dataset.stats["closing_count"].event_count == 2
    with b["db"].transaction(b["viewer"], b["business"]) as c:
        c.execute("SET LOCAL TIME ZONE 'Pacific/Auckland'")
        assert select_coverage(c, b["business"], scope, "service").dataset.signature == after.dataset.signature
        assert select_coverage(c, b["business"], scope, "production").dataset.signature != after.dataset.signature


def test_role_tenant_shape_authorship_and_append_only_guards(context):
    b, coverage, scope, _, _, _ = context
    value = submit(context)
    with pytest.raises(AccessDenied):
        coverage.decide(b["editor"], b["business"], "editor-review", value.id,
                        CoverageDecision(approved=True, reason_fa="بررسی"))
    with b["db"].transaction(b["stranger"], b["other"]) as c:
        assert c.execute("SELECT * FROM herman.coverage_assessments").fetchall() == []
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("SELECT herman.coverage_dossier(%s,%s,%s,%s,'service')",
                      (b["business"], scope.warehouse_id, scope.start, scope.end))
    with pytest.raises(psycopg.errors.CheckViolation), b["db"].transaction(b["owner"], b["business"]) as c:
        c.execute("SELECT herman.coverage_dossier(%s,%s,%s,'infinity'::timestamptz,'service')",
                  (b["business"], scope.warehouse_id, scope.start))
    with pytest.raises(NotFound):
        coverage.detail(b["stranger"], b["other"], value.id)
    with pytest.raises(psycopg.errors.InsufficientPrivilege), psycopg.connect(b["admin"]) as c:
        c.execute("UPDATE herman.coverage_assessments SET basis='production' WHERE business_id=%s AND id=%s",
                  (b["business"], value.id))
    with pytest.raises(psycopg.errors.InsufficientPrivilege), b["db"].transaction(b["owner"], b["business"]) as c:
        insert(c, "coverage_assessments", dict(business_id=b["business"], id=uuid4(), warehouse_id=scope.warehouse_id,
            period_start=scope.start, period_end=scope.end, basis="service", categories=Jsonb(value.model_dump(mode="json")["categories"]),
            document_id=value.evidence.document_id, locator="1", created_by=b["editor"]))
    with pytest.raises(psycopg.errors.CheckViolation), b["db"].transaction(b["owner"], b["business"]) as c:
        invalid = value.model_dump(mode="json")["categories"]
        invalid["sales"]["evidence"]["document_id"] = str(uuid4())
        insert(c, "coverage_assessments", dict(business_id=b["business"], id=uuid4(), warehouse_id=scope.warehouse_id,
            period_start=scope.start, period_end=scope.end, basis="service", categories=Jsonb(invalid),
            document_id=value.evidence.document_id, locator="1", created_by=b["owner"]))


def test_decision_dataset_server_derived_and_idempotency(context):
    b, coverage, *_ = context
    value = submit(context)
    with b["db"].transaction(b["owner"], b["business"], reviewer=True) as c:
        insert(c, "coverage_decisions", dict(business_id=b["business"], assessment_id=value.id,
            actor_id=b["owner"], approved=True, reason_fa="بررسی", dataset=Jsonb({"signature": "forged"}),
            decided_at=datetime(2000, 1, 1, tzinfo=timezone.utc)))
    reviewed = assess(context)
    assert reviewed.complete and reviewed.decision.dataset == reviewed.dataset
    assert reviewed.decision.decided_at.year != 2000
    successor = submit(context, proposal(context, supersedes_id=value.id))
    assert coverage.propose(b["editor"], b["business"], "proposal-" + str(successor.id), successor) == successor.id
    decide(context, successor, key="review-retry")
    assert decide(context, successor, key="review-retry") == successor.id
    with pytest.raises(Conflict):
        coverage.decide(b["owner"], b["business"], "review-retry", successor.id,
                        CoverageDecision(approved=False, reason_fa="رد"))


def test_source_hash_on_approval_rejection_remains_possible(context):
    b, coverage, *_ = context
    value = submit(context)
    with b["db"].transaction(b["owner"], b["business"]) as c:
        sha = c.execute("SELECT sha256 FROM herman.documents WHERE business_id=%s AND id=%s",
                        (b["business"], value.evidence.document_id)).fetchone()["sha256"]
    (b["blob_root"] / str(b["business"]) / sha).write_bytes(b"changed")
    with pytest.raises(ValueError):
        decide(context, value)
    assert coverage.detail(b["viewer"], b["business"], value.id)["decision"] is None
    decide(context, value, approved=False)
    assert not assess(context).complete


def test_recipe_requirement_and_operational_source_hash(context):
    b, coverage, scope, item, evidence, _ = context
    product = Item(id=uuid4(), business_id=b["business"], sku="C17-RECIPE", name_fa="محصول",
                   base_unit="each", consumption_mode="recipe")
    b["service"].catalog(b["owner"], b["business"], "product", product)
    document = b["service"].document(b["owner"], b["business"], "recipe-doc", "recipe.txt", "text/plain", b"recipe")
    recipe = Recipe(id=uuid4(), business_id=b["business"], product_id=product.id, valid_from=scope.start,
        output_quantity="1", output_unit="each", evidence=dict(document_id=document, locator="1"),
        lines=[dict(item_id=item.id, quantity="2", unit="each")])
    fulfillment = Fulfillment(id=uuid4(), business_id=b["business"], warehouse_id=scope.warehouse_id,
        product_id=product.id, occurred_at=scope.start + timedelta(days=2), quantity="1", unit="each", evidence=evidence)
    for name, record in (("recipe", recipe), ("fulfillment", fulfillment)):
        b["service"].propose(b["editor"], b["business"], name, record)
        b["service"].approve(b["owner"], b["business"], name + "-review", record.id, True, "تأیید")
    value = proposal(context)
    categories = value.model_dump()["categories"]
    categories["sales"]["status"] = "records_complete"
    value = submit(context, CoverageProposal.model_validate(dict(value.model_dump(), categories=categories)))
    decide(context, value)
    snapshot = assess(context)
    assert snapshot.dataset.required_recipe_products == 1 and not snapshot.complete
    assert snapshot.dataset.row_count == 5  # Two counts, fulfillment, recipe and one ingredient.
    categories["recipes"]["status"] = "records_complete"
    replacement = submit(context, CoverageProposal.model_validate(dict(value.model_dump(), id=uuid4(),
        supersedes_id=value.id, categories=categories)))
    with b["db"].transaction(b["viewer"], b["business"]) as c:
        sha = c.execute("SELECT sha256 FROM herman.documents WHERE business_id=%s AND id=%s",
                        (b["business"], document)).fetchone()["sha256"]
    (b["blob_root"] / str(b["business"]) / sha).write_bytes(b"tampered operational evidence")
    with pytest.raises(ValueError):
        decide(context, replacement)
    assert coverage.detail(b["viewer"], b["business"], replacement.id)["decision"] is None
    decide(context, replacement, approved=False)


def test_review_chain_root_and_successor_races(context):
    b, coverage, *_ = context
    roots = [submit(context), submit(context)]

    def attempt(value):
        try:
            decide(context, value)
            return "approved"
        except (psycopg.errors.UniqueViolation, psycopg.errors.CheckViolation, Conflict):
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(attempt, roots)) == ["approved", "conflict"]
    head = assess(context).assessment
    successors = [submit(context, proposal(context, supersedes_id=head.id)) for _ in range(2)]
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(attempt, successors)) == ["approved", "conflict"]
    current = assess(context).assessment
    assert current.id in {row.id for row in successors}
    detail = coverage.detail(b["viewer"], b["business"], head.id)
    assert detail["successor_id"] == current.id
    assert len(coverage.page(b["viewer"], b["business"], limit=2)["assessments"]) == 2


def test_provisional_does_not_promote_with_clock_passage(context):
    value = submit(context)
    decide(context, value)
    reviewed = assess(context)
    early = reviewed.decision.model_copy(update={"decided_at": reviewed.scope.end - timedelta(seconds=1)})
    provisional = reviewed.model_copy(update={"decision": early})
    assert provisional.complete and provisional.provisional
    later = provisional.model_copy(update={"as_of": provisional.as_of + timedelta(days=365)})
    assert later.provisional
    assert later.model_dump(exclude={"as_of"}) == provisional.model_dump(exclude={"as_of"})


def test_shared_row_budget_and_bounded_overflow(context):
    b, _, scope, item, evidence, _ = context
    with b["db"].transaction(b["viewer"], b["business"]) as c:
        remaining = 2

        def read(query, parameters):
            nonlocal remaining
            rows = c.execute(query + " LIMIT %s", (*parameters, remaining + 1)).fetchall()
            remaining -= len(rows)
            if remaining < 0:
                raise SelectionLimit("shared budget exhausted")
            return rows

        with pytest.raises(SelectionLimit):
            select_coverage(c, b["business"], scope, "service", read=read)
    with psycopg.connect(b["admin"]) as c:
        c.execute("SELECT set_config('herman.user_id',%s,true)", (str(b["owner"]),))
        c.execute("SELECT set_config('herman.business_id',%s,true)", (str(b["business"]),))
        c.execute("CREATE TEMP TABLE coverage_ids AS SELECT gen_random_uuid() AS id FROM generate_series(1,10001)")
        c.execute("INSERT INTO herman.records(business_id,id,kind,document_id,locator,created_by) "
            "SELECT %s,id,'count',%s,'bulk',%s FROM coverage_ids", (b["business"], evidence["document_id"], b["owner"]))
        c.execute("INSERT INTO herman.stock_counts(business_id,id,warehouse_id,item_id,occurred_at,quantity,unit) "
            "SELECT %s,id,%s,%s,%s,1,'each' FROM coverage_ids", (b["business"], scope.warehouse_id,item.id,scope.start))
    snapshot = assess(context)
    assert not snapshot.complete and not snapshot.dataset.available
    assert snapshot.dataset.signature is None and snapshot.dataset.row_count == 10001
    value = submit(context)
    with pytest.raises(psycopg.errors.CheckViolation), b["db"].transaction(b["owner"], b["business"]) as c:
        insert(c, "coverage_decisions", dict(business_id=b["business"], assessment_id=value.id,
            actor_id=b["owner"], approved=True, reason_fa="بررسی", dataset=Jsonb({})))
    # Even unavailable data can be rejected without a fabricated partial signature.
    decide(context, value, approved=False)


def test_unanalysed_bulk_tenant_dossier_has_bounded_execution(backend):
    b = backend
    # Keep every new tenant fact uncommitted so autovacuum cannot repair the
    # missing statistics that previously produced a quadratic join plan.
    with psycopg.connect(b["admin"], row_factory=dict_row) as c:
        c.execute("SELECT set_config('herman.user_id',%s,true)", (str(b["owner"]),))
        business = c.execute("SELECT herman.create_business(%s,%s,%s) AS id",
            ("آزمون پوشش", "restaurant", str(uuid4()))).fetchone()["id"]
        c.execute("SELECT set_config('herman.business_id',%s,true)", (str(business),))
        warehouse, item, document = uuid4(), uuid4(), uuid4()
        insert(c, "warehouses", dict(business_id=business, id=warehouse, name="انبار"))
        insert(c, "items", dict(business_id=business, id=item, sku="BULK", name_fa="قلم",
                                base_unit="each", consumption_mode="direct"))
        insert(c, "documents", dict(business_id=business, id=document, sha256="0" * 64,
            original_name="شاهد", media_type="text/plain", byte_size=1, created_by=b["owner"]))
        scope = Scope(business_id=business, warehouse_id=warehouse,
            start=datetime(2026, 9, 1, tzinfo=timezone.utc), end=datetime(2026, 10, 1, tzinfo=timezone.utc))
        c.execute("CREATE TEMP TABLE unanalysed_coverage_ids AS SELECT gen_random_uuid() AS id "
                  "FROM generate_series(1,10001)")
        c.execute("INSERT INTO herman.records(business_id,id,kind,document_id,locator,created_by) "
            "SELECT %s,id,'count',%s,'شمارش',%s FROM unanalysed_coverage_ids", (business, document, b["owner"]))
        c.execute("INSERT INTO herman.stock_counts(business_id,id,warehouse_id,item_id,occurred_at,quantity,unit) "
            "SELECT %s,id,%s,%s,%s,1,'each' FROM unanalysed_coverage_ids", (business, warehouse, item, scope.start))
        c.execute("SET LOCAL ROLE herman_app")
        c.execute("SET LOCAL statement_timeout='10s'")
        snapshot = select_coverage(c, business, scope, "service")
        assert not snapshot.dataset.available and snapshot.dataset.row_count == 10001
        assert c.execute("SELECT current_setting('statement_timeout') AS setting").fetchone()["setting"] == "10s"
        c.rollback()
