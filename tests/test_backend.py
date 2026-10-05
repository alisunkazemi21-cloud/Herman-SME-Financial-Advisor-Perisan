"""Real PostgreSQL acceptance tests. Set HERMAN_TEST_ADMIN_DSN to a disposable database."""
# ruff: noqa: E402
import hashlib
import os
import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

psycopg = pytest.importorskip("psycopg")
pytest.importorskip("fastapi")
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.conninfo import make_conninfo
from test_inventory import inventory_payload as inventory_fixture

from src.backend.api import create_app
from src.backend.database import AccessDenied, Database, migrate
from src.backend.inventory import Count, Fulfillment, Item, Movement, Recipe
from src.backend.service import AnalysisInput, Conflict, Service, Warehouse

inventory_payload = inventory_fixture


@pytest.fixture(scope="module")
def database():
    admin = os.environ.get("HERMAN_TEST_ADMIN_DSN")
    if not admin:
        pytest.skip("real PostgreSQL acceptance requires HERMAN_TEST_ADMIN_DSN")
    migrate(admin)
    login, password = "test_" + uuid4().hex, secrets.token_hex(32)
    with psycopg.connect(admin) as c:
        c.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {} IN ROLE herman_app").format(
            sql.Identifier(login), sql.Literal(password)))
    yield Database(make_conninfo(admin, user=login, password=password)), admin
    with psycopg.connect(admin) as c:
        c.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(login)))


@pytest.fixture
def backend(database, tmp_path):
    db, admin = database
    owner, stranger, editor, viewer = [uuid4() for _ in range(4)]
    tokens = [secrets.token_urlsafe(48) for _ in range(4)]
    with psycopg.connect(admin) as c:
        for identity, token in zip((owner, stranger, editor, viewer), tokens):
            c.execute("INSERT INTO herman.users(id,display_name) VALUES(%s,%s)", (identity, "test"))
            c.execute("INSERT INTO herman.api_credentials(digest,user_id,expires_at) VALUES(%s,%s,%s)",
                      (hashlib.sha256(token.encode()).hexdigest(), identity,
                       datetime.now(timezone.utc) + timedelta(days=1)))
    service = Service(db, tmp_path / "blobs")
    business = service.create_business(owner, "رستوران نمونه", "restaurant", "create")
    other = service.create_business(stranger, "کافه دیگر", "cafe", "create")
    with psycopg.connect(admin) as c:
        for identity, role in ((editor, "editor"), (viewer, "viewer")):
            c.execute("INSERT INTO herman.memberships(business_id,user_id,role) VALUES(%s,%s,%s)",
                      (business, identity, role))
    return dict(db=db, admin=admin, service=service, owner=owner, stranger=stranger, editor=editor,
                viewer=viewer, business=business, other=other, tokens=tokens, blob_root=tmp_path / "blobs")


def test_rls_composite_foreign_keys_and_immutable_records(backend):
    b = backend
    db, service = b["db"], b["service"]
    item = Item(id=uuid4(), business_id=b["business"], sku="x", name_fa="کالا", base_unit="g")
    service.catalog(b["owner"], b["business"], "item", item)
    with db.transaction(b["stranger"], b["other"]) as c:
        # Deliberately omit tenant predicate; RLS still hides the other tenant.
        assert c.execute("SELECT * FROM herman.items").fetchall() == []
    with pytest.raises(AccessDenied), db.transaction(b["stranger"], b["business"]):
        pass
    with psycopg.connect(db.dsn) as c:
        assert c.execute("SELECT * FROM herman.items").fetchall() == []  # unset context
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("SELECT * FROM herman.api_credentials")
    with pytest.raises(psycopg.errors.InsufficientPrivilege), db.transaction(b["owner"], b["business"]) as c:
        c.execute("UPDATE herman.items SET name_fa='changed'")
    with pytest.raises(psycopg.errors.InsufficientPrivilege), psycopg.connect(b["admin"]) as c:
        # Even a privileged accidental update hits append-only trigger.
        c.execute("UPDATE herman.items SET name_fa='changed' WHERE business_id=%s", (b["business"],))
    warehouse = Warehouse(id=uuid4(), business_id=b["other"], name="انبار")
    service.catalog(b["stranger"], b["other"], "warehouse", warehouse)
    document = service.document(b["stranger"], b["other"], "document", "evidence.txt", "text/plain", b"evidence")
    record = Count(id=uuid4(), business_id=b["other"], warehouse_id=warehouse.id, item_id=item.id,
                   occurred_at=datetime.now(timezone.utc), quantity="1", unit="g",
                   evidence=dict(document_id=document, locator="1"))
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        service.propose(b["stranger"], b["other"], "bad-cross-tenant-item", record)
    with db.transaction(b["stranger"], b["other"]) as c:
        assert not c.execute("SELECT 1 FROM herman.records WHERE id=%s", (record.id,)).fetchone()
        assert not c.execute("SELECT 1 FROM herman.idempotency_keys WHERE key='bad-cross-tenant-item'").fetchone()


def test_authenticated_roles_and_document_access(backend):
    b = backend
    service, db = b["service"], b["db"]
    assert db.authenticate(b["tokens"][0]) == b["owner"]
    with pytest.raises(AccessDenied):
        db.authenticate("invalid" * 10)
    with pytest.raises(AccessDenied):
        service.document(b["viewer"], b["business"], "x", "x", "text/plain", b"x")
    document = service.document(b["editor"], b["business"], "doc", "../../escape.txt", "text/plain", b"secret")
    assert service.read_document(b["owner"], b["business"], document)[1] == b"secret"
    with pytest.raises(AccessDenied):
        service.read_document(b["stranger"], b["business"], document)
    with pytest.raises(AccessDenied):
        service.approve(b["editor"], b["business"], "approve", uuid4(), True, "reason")
    with pytest.raises(psycopg.errors.InsufficientPrivilege), db.transaction(b["editor"], b["business"]) as c:
        c.execute("INSERT INTO herman.approvals VALUES(%s,%s,true,%s,'forged',now())",
                  (b["business"], uuid4(), b["editor"]))
    with pytest.raises(psycopg.errors.InsufficientPrivilege), db.transaction(b["owner"], b["business"]) as c:
        c.execute("INSERT INTO herman.audit_events VALUES(%s,%s,%s,'forged',NULL,%s,now())",
                  (b["business"], uuid4(), b["stranger"], uuid4()))
    with psycopg.connect(b["admin"]) as c:
        c.execute("UPDATE herman.api_credentials SET revoked=true WHERE user_id=%s", (b["owner"],))
    with pytest.raises(AccessDenied):
        db.authenticate(b["tokens"][0])


def test_retry_concurrency_and_conflict(backend):
    b = backend
    service = b["service"]
    warehouse = Warehouse(id=uuid4(), business_id=b["business"], name="انبار")
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: service.catalog(b["owner"], b["business"], "same-key", warehouse), range(8)))
    assert set(results) == {warehouse.id}
    with b["db"].transaction(b["owner"], b["business"]) as c:
        assert c.execute("SELECT count(*) AS n FROM herman.audit_events WHERE action='warehouses.created'").fetchone()["n"] == 1
    with pytest.raises(Conflict):
        service.catalog(b["owner"], b["business"], "same-key", warehouse.model_copy(update={"name": "different"}))
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: service.create_business(b["owner"], "new", "cafe", "retry-business"), range(4)))
    assert len(set(results)) == 1
    with pytest.raises(Conflict):
        service.create_business(b["owner"], "different", "cafe", "retry-business")


def seed_inventory(b, p):
    service, actor, business = b["service"], b["owner"], b["business"]
    p["scope"]["business_id"] = str(business)
    warehouse = UUID(p["scope"]["warehouse_id"])
    service.catalog(actor, business, "warehouse", Warehouse(id=warehouse, business_id=business, name="انبار"))
    document = service.document(actor, business, "source", "inventory.txt", "text/plain", b"synthetic inventory")
    for item in p["items"]:
        item["business_id"] = str(business)
        service.catalog(actor, business, item["id"], Item.model_validate(item))
    for kind, rows in ((Count, [p["opening"], p["closing"]]), (Movement, p["movements"]),
                       (Recipe, p["recipes"]), (Fulfillment, p["fulfillments"])):
        for row in rows:
            row.update(business_id=str(business), status="proposed")
            row["evidence"] = dict(document_id=str(document), locator="synthetic:1")
            value = kind.model_validate(row)
            service.propose(actor, business, "propose:" + row["id"], value)
            service.approve(actor, business, "approve:" + row["id"], value.id, True, "بررسی نمونه ساختگی")
    for field in ("coverage", "policy"):
        p[field]["evidence"] = dict(document_id=str(document), locator="synthetic:coverage")
    return AnalysisInput(scope=p["scope"], target_item_id=p["target_item_id"], opening_id=p["opening"]["id"],
                         closing_id=p["closing"]["id"], coverage=p["coverage"], policy=p["policy"])


def test_persisted_vertical_slice_and_quick_no_history(backend, inventory_payload):
    b = backend
    value = seed_inventory(b, inventory_payload)
    identity = b["service"].analyze(b["owner"], b["business"], "analysis", value)
    saved = b["service"].analysis(b["owner"], b["business"], identity)
    assert saved["result"]["status"] == "complete"
    assert float(saved["result"]["unexplained_shortage"]) == 7000
    assert saved["input_snapshot"]["opening"]["status"] == "approved"
    assert b["service"].analyze(b["owner"], b["business"], "analysis", value) == identity
    with TestClient(create_app(b["db"], b["blob_root"])) as client:
        headers = {"Authorization": "Bearer " + b["tokens"][0]}
        assert client.get("/businesses").status_code == 401
        response = client.get("/businesses", headers=headers)
        assert response.status_code == 200, response.text
        assert len(response.json()) == 1
        response = client.get(f"/businesses/{b['business']}/resources/records?limit=2", headers=headers)
        assert response.status_code == 200
        assert len(response.json()) == 2
        first_record = response.json()[0]["id"]
        detail = client.get(f"/businesses/{b['business']}/records/{first_record}", headers=headers)
        assert detail.status_code == 200
        assert detail.json()["decision"]["approved"] is True
        assert client.get(f"/businesses/{b['other']}/resources/documents", headers=headers).status_code == 403
        response = client.get(f"/businesses/{b['other']}/inventory-analyses/{identity}", headers=headers)
        assert response.status_code == 403
        # Supply missing data in Quick: it must not retrieve counts from the saved business.
        inventory_payload["opening"] = None
        response = client.post("/quick/inventory", json=inventory_payload, headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "incomplete"
        assert response.headers["cache-control"] == "no-store"
        response = client.post(f"/businesses/{b['business']}/inventory-analyses",
            json=value.model_dump(mode="json"), headers={**headers, "Idempotency-Key": "api-analysis"})
        assert response.status_code == 201, response.text
        assert response.json()["result"]["status"] == "complete"
    with b["db"].transaction(b["owner"], b["business"]) as c:
        assert c.execute("SELECT count(*) AS n FROM herman.analysis_runs").fetchone()["n"] == 2


def test_proposed_data_and_missing_evidence_fail_closed(backend, inventory_payload):
    b = backend
    value = seed_inventory(b, inventory_payload)
    row = dict(inventory_payload["movements"][0], id=str(uuid4()))
    b["service"].propose(b["editor"], b["business"], "pending", Movement.model_validate(row))
    identity = b["service"].analyze(b["owner"], b["business"], "incomplete", value)
    assert b["service"].analysis(b["owner"], b["business"], identity)["result"]["unexplained_shortage"] is None
    forged = dict(row, id=str(uuid4()), status="approved")
    with pytest.raises(ValueError):
        b["service"].propose(b["owner"], b["business"], "forged", Movement.model_validate(forged))
    doc_id = UUID(inventory_payload["opening"]["evidence"]["document_id"])
    metadata, _ = b["service"].read_document(b["owner"], b["business"], doc_id)
    (b["blob_root"] / str(b["business"]) / metadata["sha256"]).write_bytes(b"tampered")
    with pytest.raises(Conflict, match="شاهد"):
        b["service"].analyze(b["owner"], b["business"], "tampered", value)
    with b["db"].transaction(b["owner"], b["business"]) as c:
        assert not c.execute("SELECT 1 FROM herman.idempotency_keys WHERE key='tampered'").fetchone()


def test_superuser_runtime_rejected(database):
    _, admin = database
    with pytest.raises(ValueError, match="unprivileged"):
        Database(admin)
