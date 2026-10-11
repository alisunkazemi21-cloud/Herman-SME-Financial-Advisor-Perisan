"""Reviewed whole-record corrections and immutable inventory calculation receipts."""

# ruff: noqa: E402
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from decimal import Decimal
from threading import Barrier
from uuid import UUID, uuid4

import pytest

psycopg = pytest.importorskip("psycopg")
pytest.importorskip("fastapi")
from fastapi.testclient import TestClient
from test_backend import backend as backend_fixture
from test_backend import database as database_fixture
from test_backend import inventory_payload as inventory_fixture
from test_backend import seed_inventory
from test_tabular_imports import source

from src.backend import inventory_history
from src.backend.advisor import BusinessAdvisor, BusinessContextInput
from src.backend.api import create_app
from src.backend.database import AccessDenied, migrate
from src.backend.imports import TabularImport, TabularImporter
from src.backend.inventory import Count, Fulfillment, Movement, Recipe, RecipeLine
from src.backend.service import Conflict, NotFound, insert

backend = backend_fixture
database = database_fixture
inventory_payload = inventory_fixture
KINDS = {"count": Count, "movement": Movement, "recipe": Recipe, "fulfillment": Fulfillment}


def revised(payload, kind, **changes):
    original = payload["closing"] if kind == "count" else payload[
        {"movement": "movements", "recipe": "recipes", "fulfillment": "fulfillments"}[kind]][0]
    value = deepcopy(original)
    value.update(id=str(uuid4()), status="proposed", **changes)
    return UUID(original["id"]), KINDS[kind].model_validate(value)


def correct(b, predecessor, value, key="correction"):
    return b["service"].correct_inventory(b["editor"], b["business"], key, predecessor, value)


def review(b, identity, key="review-correction", approved=True, resolution=None):
    return b["service"].approve(b["owner"], b["business"], key, identity, approved,
                                 "اصلاح با شاهد بررسی شد", resolution)


def analyze(b, value, key):
    identity = b["service"].analyze(b["owner"], b["business"], key, value)
    return b["service"].analysis(b["viewer"], b["business"], identity)


@pytest.mark.parametrize("kind,shortage,usage", [
    ("count", "0", "120000"), ("movement", "27000", "120000"),
    ("recipe", "27000", "100000"), ("fulfillment", "19000", "108000"),
])
def test_each_record_kind_reconciles_corrected_values_and_retains_history(backend, inventory_payload,
                                                                         kind, shortage, usage):
    b = backend
    value = seed_inventory(b, inventory_payload)
    before = analyze(b, value, "before")
    changes = {"quantity": {"count": "25", "movement": "70", "fulfillment": "900"}.get(kind)}
    if kind == "recipe":
        changes = dict(lines=[{**inventory_payload["recipes"][0]["lines"][0], "quantity": "0.1"}])
    predecessor, replacement = revised(inventory_payload, kind, **changes)
    original = b["service"].record(b["viewer"], b["business"], predecessor)
    identity = correct(b, predecessor, replacement)
    assert analyze(b, value, "pending")["result"] == before["result"]
    review(b, identity)
    if kind == "count":
        with pytest.raises(Conflict, match=str(identity)):
            analyze(b, value, "stale-count")
        value = value.model_copy(update={"closing_id": identity})
    after = analyze(b, value, "after")
    assert after["result"]["status"] == "complete"
    assert Decimal(after["result"]["unexplained_shortage"]) == Decimal(shortage)
    assert Decimal(after["result"]["expected_usage"]) == Decimal(usage)
    assert [row["id"] for row in after["correction_provenance"]] == [str(identity), str(predecessor)]
    assert after["correction_provenance"][0]["document_sha256"]
    retained = b["service"].record(b["viewer"], b["business"], predecessor)
    assert retained["state"] == "superseded" and retained["superseded_by"] == identity
    assert retained["source"] == original["source"] and retained["detail"] == original["detail"]
    assert b["service"].analysis(b["viewer"], b["business"], before["id"]) == before
    assert analyze(b, value, "after") == after
    context = BusinessAdvisor(b["service"]).context(b["viewer"], b["business"], BusinessContextInput(
        question_fa="اختلاف پس از اصلاح چیست؟", effective_at=value.scope.end, analysis_id=after["id"]))
    assert context["analysis"]["correction_provenance"] == after["correction_provenance"]


def test_rejected_correction_leaves_current_data_and_allows_another_candidate(backend, inventory_payload):
    b = backend
    value = seed_inventory(b, inventory_payload)
    predecessor, replacement = revised(inventory_payload, "movement", quantity="70")
    rejected = correct(b, predecessor, replacement)
    review(b, rejected, approved=False)
    assert Decimal(analyze(b, value, "after-reject")["result"]["unexplained_shortage"]) == 7000
    accepted = correct(b, predecessor, replacement.model_copy(update={"id": uuid4()}), "second")
    review(b, accepted, "second-review")
    assert Decimal(analyze(b, value, "after-accept")["result"]["unexplained_shortage"]) == 27000


@pytest.mark.parametrize("kind", ["movement", "fulfillment", "recipe"])
def test_corrected_time_or_validity_has_no_fallback(backend, inventory_payload, kind):
    b = backend
    value = seed_inventory(b, inventory_payload)
    changes = {"valid_from" if kind == "recipe" else "occurred_at": value.scope.end}
    predecessor, replacement = revised(inventory_payload, kind, **changes)
    identity = correct(b, predecessor, replacement)
    review(b, identity)
    after = analyze(b, value, "after")
    if kind == "recipe":
        assert after["result"]["status"] == "incomplete"
        assert after["result"]["unexplained_shortage"] is None
    else:
        # Purchase moved out removes 50 kg; fulfillment moved out removes 120 kg usage.
        assert Decimal(after["result"]["unexplained_shortage"]) == (-43000 if kind == "movement" else 127000)
    assert after["correction_provenance"] == []  # No corrected event was in this selected period.


def test_same_event_ancestry_is_excluded_but_independent_duplicate_still_needs_review(backend, inventory_payload):
    b = backend
    seed_inventory(b, inventory_payload)
    predecessor, same = revised(inventory_payload, "movement")
    first = correct(b, predecessor, same)
    competing = correct(b, predecessor, same.model_copy(update={"id": uuid4()}), "competing")
    assert not b["service"].record(b["viewer"], b["business"], first)["duplicate_candidates"]["requires_resolution"]
    review(b, first)
    with pytest.raises(Conflict):
        review(b, competing, "lost")
    review(b, competing, "reject-lost", approved=False)
    independent = same.model_copy(update={"id": uuid4()})
    b["service"].propose(b["editor"], b["business"], "independent", independent)
    next_value = same.model_copy(update={"id": uuid4()})
    next_id = correct(b, first, next_value, "next")
    matches = b["service"].record(b["viewer"], b["business"], next_id)["duplicate_candidates"]
    assert [row["id"] for row in matches["records"]] == [independent.id]
    with pytest.raises(Conflict):
        review(b, next_id, "without-resolution")
    review(b, next_id, "with-resolution", resolution="distinct_event")


def test_renamed_identical_ancestor_document_does_not_require_false_distinct_event(backend, inventory_payload):
    b = backend
    seed_inventory(b, inventory_payload)
    predecessor, value = revised(inventory_payload, "movement")
    _, content = b["service"].read_document(b["owner"], b["business"], value.evidence.document_id)
    document = b["service"].document(b["owner"], b["business"], "renamed", "new-name.txt", "text/plain", content)
    value = value.model_copy(update={"evidence": value.evidence.model_copy(update={"document_id": document})})
    identity = correct(b, predecessor, value)
    assert not b["service"].record(b["viewer"], b["business"], identity)["duplicate_candidates"]["documents"]
    review(b, identity)


def test_import_row_lineage_survives_multiple_corrections_and_reimport_stays_blocked(backend, inventory_payload):
    b = backend
    value = seed_inventory(b, inventory_payload)
    extraction = source(b)
    mapping = TabularImport(extraction_id=extraction, sheet="CSV", rows=[2], record_kind="movement",
        warehouse_id=value.scope.warehouse_id, sku_column="sku", quantity_column="quantity",
        unit_column="unit", time_column="time", movement_kind="purchase")
    importer = TabularImporter(b["service"])
    batch = importer.create(b["owner"], b["business"], "import", mapping)
    original = importer.read(b["owner"], b["business"], batch)["records"][0]["id"]
    review(b, original, "original-review")
    detail = b["service"].record(b["viewer"], b["business"], original)
    replacement = Movement(**{**detail["detail"], "id": uuid4(), "quantity": "7"},
                           evidence=dict(document_id=detail["source"]["document_id"], locator="CSV:row:2"))
    first = correct(b, original, replacement)
    review(b, first)
    second = correct(b, first, replacement.model_copy(update={"id": uuid4(), "quantity": Decimal("8")}), "next")
    review(b, second, "next-review")
    result = analyze(b, value, "analysis")
    assert Decimal(result["result"]["unexplained_shortage"]) == 15000  # baseline 7 + corrected 8 kg
    assert result["source_provenance"] == []
    lineage = result["correction_provenance"]
    assert [row["id"] for row in lineage] == [str(second), str(first), str(original)]
    assert lineage[0]["import_origin"] is None and lineage[1]["import_origin"] is None
    assert lineage[2]["import_origin"]["extraction_id"] == str(extraction)
    assert lineage[2]["import_origin"]["source_values"]["quantity"] == "5"
    with pytest.raises(Conflict):
        importer.create(b["owner"], b["business"], "repeat", mapping)


def test_concurrent_corrections_have_one_approved_successor(backend, inventory_payload, monkeypatch):
    b = backend
    value = seed_inventory(b, inventory_payload)
    predecessor, replacement = revised(inventory_payload, "movement", quantity="70")
    candidates = [correct(b, predecessor, replacement.model_copy(update={"id": uuid4()}), f"c-{i}")
                  for i in range(2)]
    barrier = Barrier(2)
    original = b["service"]._inventory_evidence

    def synchronized(*args):
        original(*args)
        barrier.wait(timeout=20)

    monkeypatch.setattr(b["service"], "_inventory_evidence", synchronized)

    def attempt(identity):
        try:
            return review(b, identity, str(identity))
        except psycopg.errors.UniqueViolation as exc:
            assert exc.diag.constraint_name == "inventory_one_replacement"
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        winners = [identity for identity in pool.map(attempt, candidates) if identity is not None]
    assert len(winners) == 1
    monkeypatch.setattr(b["service"], "_inventory_evidence", original)
    assert Decimal(analyze(b, value, "after")["result"]["unexplained_shortage"]) == 27000
    loser = next(identity for identity in candidates if identity not in winners)
    with b["db"].transaction(b["owner"], b["business"]) as c:
        assert not c.execute("SELECT 1 FROM herman.idempotency_keys WHERE key=%s", (str(loser),)).fetchone()
        assert not c.execute("SELECT 1 FROM herman.audit_events WHERE action='record.reviewed' AND entity_id=%s",
                             (loser,)).fetchone()


def test_correction_access_validation_and_evidence_integrity(backend, inventory_payload):
    b = backend
    seed_inventory(b, inventory_payload)
    predecessor, replacement = revised(inventory_payload, "movement", quantity="70")
    with pytest.raises(AccessDenied):
        b["service"].correct_inventory(b["viewer"], b["business"], "viewer", predecessor, replacement)
    with pytest.raises(NotFound):
        b["service"].correct_inventory(b["stranger"], b["other"], "foreign", predecessor, replacement)
    with pytest.raises(Conflict):
        correct(b, UUID(inventory_payload["closing"]["id"]), replacement, "wrong-kind")
    identity = correct(b, predecessor, replacement)
    with pytest.raises(Conflict):
        correct(b, identity, replacement.model_copy(update={"id": uuid4()}), "pending-parent")
    metadata, _ = b["service"].read_document(b["owner"], b["business"], replacement.evidence.document_id)
    (b["blob_root"] / str(b["business"]) / metadata["sha256"]).write_bytes(b"tampered")
    with pytest.raises(Conflict):
        review(b, identity)
    assert b["service"].record(b["viewer"], b["business"], identity)["state"] == "pending"


def test_api_correction_discriminator_history_and_cache_policy(backend, inventory_payload):
    b = backend
    seed_inventory(b, inventory_payload)
    predecessor, replacement = revised(inventory_payload, "movement", quantity="999999999999999999.123456")
    headers = {"Authorization": "Bearer " + b["tokens"][0], "Idempotency-Key": "api"}
    base = f"/businesses/{b['business']}/records"
    body = dict(record_kind="movement", replacement=replacement.model_dump(mode="json"))
    with TestClient(create_app(b["db"], b["blob_root"])) as client:
        assert client.post(base + f"/{predecessor}/corrections", json=body).status_code == 401
        response = client.post(base + f"/{predecessor}/corrections", headers=headers, json=body)
        assert response.status_code == 201, response.text
        assert response.headers["cache-control"] == "no-store"
        identity = response.json()["id"]
        response = client.post(base + f"/{identity}/decision", headers={**headers, "Idempotency-Key": "review"},
                               json=dict(approved=True, reason_fa="بررسی شد"))
        assert response.status_code == 201, response.text
        page = client.get(base, headers=headers, params=dict(state="superseded", kind="movement", limit=1))
        assert page.status_code == 200 and page.headers["cache-control"] == "no-store"
        assert page.json()["records"][0]["id"] == str(predecessor)
        assert page.json()["records"][0]["superseded_by"] == identity
        assert "created_xid" not in page.json()["records"][0]
        detail = client.get(base + "/" + identity, headers=headers)
        assert detail.status_code == 200 and detail.headers["cache-control"] == "no-store"
        assert detail.json()["source"]["supersedes"] == str(predecessor)
        assert detail.json()["detail"]["quantity"] == "999999999999999999.123456"
        bad = {**body, "record_kind": "count"}
        assert client.post(base + f"/{predecessor}/corrections", headers=headers, json=bad).status_code == 422
        assert client.get(base, headers=headers, params=dict(state="unknown")).status_code == 422
        assert client.get(base, headers=headers, params=dict(limit=51)).status_code == 422
    assert b["service"].inventory_records(b["stranger"], b["other"], supersedes=predecessor)["records"] == []


def test_lineage_bound_fails_without_partial_analysis(backend, inventory_payload, monkeypatch):
    b = backend
    value = seed_inventory(b, inventory_payload)
    predecessor, replacement = revised(inventory_payload, "movement", quantity="70")
    identity = correct(b, predecessor, replacement)
    review(b, identity)
    monkeypatch.setattr(inventory_history, "MAX_LINEAGE_ROWS", 1)
    with pytest.raises(ValueError):
        analyze(b, value, "too-large")
    with b["db"].transaction(b["owner"], b["business"]) as c:
        assert not c.execute("SELECT 1 FROM herman.analysis_runs").fetchone()
        assert not c.execute("SELECT 1 FROM herman.idempotency_keys WHERE key='too-large'").fetchone()
    monkeypatch.setattr(inventory_history, "MAX_LINEAGE_ROWS", 10000)
    monkeypatch.setattr(inventory_history, "MAX_LINEAGE_BYTES", 1)
    with pytest.raises(ValueError):
        analyze(b, value, "too-large-bytes")


def test_database_seals_recipe_lines_and_rejects_wrong_or_missing_detail(backend, inventory_payload):
    b = backend
    seed_inventory(b, inventory_payload)
    recipe = UUID(inventory_payload["recipes"][0]["id"])
    with pytest.raises(psycopg.errors.CheckViolation), b["db"].transaction(b["owner"], b["business"]) as c:
        insert(c, "recipe_lines", dict(business_id=b["business"], recipe_id=recipe,
            item_id=inventory_payload["items"][1]["id"], quantity="1", unit="each", basis="raw", preparation_yield="1"))
    doc = inventory_payload["opening"]["evidence"]["document_id"]
    for missing in (True, False):
        with pytest.raises(psycopg.errors.CheckViolation), b["db"].transaction(b["owner"], b["business"]) as c:
            identity = uuid4()
            insert(c, "records", dict(business_id=b["business"], id=identity, kind="recipe",
                document_id=doc, locator="خط ۱", created_by=b["owner"]))
            if not missing:
                insert(c, "stock_counts", dict(business_id=b["business"], id=identity,
                    warehouse_id=inventory_payload["scope"]["warehouse_id"], item_id=inventory_payload["target_item_id"],
                    occurred_at=inventory_payload["scope"]["end"], quantity="1", unit="kg"))


def test_database_derives_predecessor_and_keeps_links_immutable(backend, inventory_payload):
    b = backend
    seed_inventory(b, inventory_payload)
    predecessor, replacement = revised(inventory_payload, "movement", quantity="70")
    first = correct(b, predecessor, replacement)
    second = correct(b, predecessor, replacement.model_copy(update={"id": uuid4()}), "second")
    fields = dict(business_id=b["business"], record_id=first, approved=True, actor_id=b["owner"],
                  reason_fa="بررسی شد", supersedes=uuid4())
    with b["db"].transaction(b["owner"], b["business"]) as c:
        insert(c, "approvals", fields)
    assert b["service"].record(b["viewer"], b["business"], first)["decision"]["supersedes"] == predecessor
    with pytest.raises(psycopg.errors.UniqueViolation), b["db"].transaction(b["owner"], b["business"]) as c:
        insert(c, "approvals", {**fields, "record_id": second, "supersedes": None})
    with pytest.raises(psycopg.errors.InsufficientPrivilege), psycopg.connect(b["admin"]) as c:
        c.execute("UPDATE herman.records SET supersedes=NULL WHERE id=%s", (first,))
    migrate(b["admin"])
    assert b["service"].record(b["viewer"], b["business"], predecessor)["superseded_by"] == first


def test_count_selection_requires_approval_and_points_to_latest_revision(backend, inventory_payload):
    b = backend
    value = seed_inventory(b, inventory_payload)
    predecessor, replacement = revised(inventory_payload, "count", quantity="25")
    first = correct(b, predecessor, replacement)
    with pytest.raises(Conflict):
        analyze(b, value.model_copy(update={"closing_id": first}), "pending-count")
    review(b, first)
    second = correct(b, first, replacement.model_copy(update={"id": uuid4(), "quantity": Decimal("20")}), "next")
    review(b, second, "next-review")
    for stale in [predecessor, first]:
        with pytest.raises(Conflict, match=str(second)):
            analyze(b, value.model_copy(update={"closing_id": stale}), str(stale))
    result = analyze(b, value.model_copy(update={"closing_id": second}), "current")
    assert Decimal(result["result"]["unexplained_shortage"]) == 5000


def test_recipe_yield_cannot_be_silently_rounded_on_persistence():
    for value in ["0.8" + "0" * 50 + "1", "0.8000001"]:
        with pytest.raises(ValueError):
            RecipeLine(item_id=uuid4(), quantity="1", unit="kg", basis="net", preparation_yield=value)
    assert RecipeLine(item_id=uuid4(), quantity="1", unit="kg", basis="net",
                      preparation_yield="0.8000000").preparation_yield == Decimal("0.8")


def test_correction_and_review_retries_remain_exact_after_later_revisions(backend, inventory_payload):
    b = backend
    seed_inventory(b, inventory_payload)
    predecessor, replacement = revised(inventory_payload, "movement", quantity="70")
    with ThreadPoolExecutor(max_workers=3) as pool:
        identities = list(pool.map(lambda _: correct(b, predecessor, replacement), range(3)))
    assert identities == [replacement.id] * 3
    review(b, replacement.id)
    next_value = replacement.model_copy(update={"id": uuid4(), "quantity": Decimal("80")})
    second = correct(b, replacement.id, next_value, "second")
    review(b, second, "second-review")
    assert correct(b, predecessor, replacement) == replacement.id
    assert review(b, replacement.id) == replacement.id
    with pytest.raises(Conflict):
        correct(b, predecessor, next_value)
    with pytest.raises(Conflict):
        correct(b, predecessor, next_value, "stale-parent")


def test_same_transaction_review_seals_recipe_lines(backend, inventory_payload):
    b = backend
    seed_inventory(b, inventory_payload)
    predecessor, replacement = revised(inventory_payload, "recipe")
    service = b["service"]
    with pytest.raises(psycopg.errors.CheckViolation), b["db"].transaction(b["owner"], b["business"]) as c:
        service._insert_proposal(c, b["owner"], b["business"], replacement, predecessor)
        c.execute("SET CONSTRAINTS ALL IMMEDIATE")
        insert(c, "approvals", dict(business_id=b["business"], record_id=replacement.id,
            approved=True, actor_id=b["owner"], reason_fa="بررسی شد"))
        insert(c, "recipe_lines", dict(business_id=b["business"], recipe_id=replacement.id,
            item_id=inventory_payload["items"][1]["id"], quantity="1", unit="each", basis="raw", preparation_yield="1"))
    with pytest.raises(NotFound):
        service.record(b["owner"], b["business"], replacement.id)
    # Even a pending recipe cannot acquire additional lines in a later transaction.
    identity = correct(b, predecessor, replacement)
    with pytest.raises(psycopg.errors.CheckViolation), b["db"].transaction(b["owner"], b["business"]) as c:
        insert(c, "recipe_lines", dict(business_id=b["business"], recipe_id=identity,
            item_id=inventory_payload["items"][1]["id"], quantity="1", unit="each", basis="raw", preparation_yield="1"))


def test_corrections_cannot_forge_import_origins_and_original_origins_are_sealed(backend, inventory_payload):
    b = backend
    value = seed_inventory(b, inventory_payload)
    extraction = source(b)
    importer = TabularImporter(b["service"])
    mapping = TabularImport(extraction_id=extraction, sheet="CSV", rows=[2], record_kind="movement",
        warehouse_id=value.scope.warehouse_id, sku_column="sku", quantity_column="quantity",
        unit_column="unit", time_column="time", movement_kind="purchase")
    batch = importer.create(b["owner"], b["business"], "import", mapping)
    original = importer.read(b["owner"], b["business"], batch)["records"][0]["id"]
    review(b, original)
    record = b["service"].record(b["owner"], b["business"], original)
    replacement = Movement(**{**record["detail"], "id": uuid4(), "quantity": "7"},
        evidence=dict(document_id=record["source"]["document_id"], locator="CSV:row:2"))
    fields = {key: record["origin"][key] for key in (
        "business_id", "id", "batch_id", "extraction_id", "document_id", "sheet", "source_row", "record_kind")}
    fields.update(source_row=3, source_values=psycopg.types.json.Jsonb({"quantity": "7"}), created_by=b["owner"])
    with pytest.raises(psycopg.errors.CheckViolation, match="inserted with unreviewed header"), (
        b["db"].transaction(b["owner"], b["business"])
    ) as c:
        b["service"]._insert_proposal(c, b["owner"], b["business"], replacement, original)
        insert(c, "record_sources", {**fields, "id": replacement.id})
    with pytest.raises(psycopg.errors.CheckViolation, match="inserted with unreviewed header"), (
        b["db"].transaction(b["owner"], b["business"])
    ) as c:
        insert(c, "record_sources", fields)


@pytest.mark.parametrize("kind", ["self", "pending", "rejected", "foreign", "different_kind"])
def test_database_rejects_invalid_predecessor_links(backend, inventory_payload, kind):
    b = backend
    seed_inventory(b, inventory_payload)
    predecessor, replacement = revised(inventory_payload, "movement", quantity="70")
    if kind in ("pending", "rejected"):
        predecessor = correct(b, predecessor, replacement)
        if kind == "rejected":
            review(b, predecessor, approved=False)
    if kind == "self":
        predecessor = replacement.id
    if kind == "different_kind":
        predecessor = UUID(inventory_payload["closing"]["id"])
    business, actor = (b["other"], b["stranger"]) if kind == "foreign" else (b["business"], b["owner"])
    with pytest.raises(psycopg.errors.CheckViolation), b["db"].transaction(actor, business) as c:
        insert(c, "records", dict(business_id=business, id=uuid4() if kind != "self" else replacement.id,
            kind="movement", document_id=replacement.evidence.document_id, locator="خط ۱",
            created_by=actor, supersedes=predecessor))
