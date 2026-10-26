"""Catalog eligibility is not authority for a concrete historical quantity."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_backend import backend as backend_fixture
from test_backend import database as database_fixture
from test_catalog import catalog as catalog_fixture

from src.backend.api import create_app
from src.backend.inventory import Count, Item
from src.backend.service import Warehouse

backend = backend_fixture
database = database_fixture
catalog = catalog_fixture


def test_definition_detail_and_history_do_not_resolve_a_past_use(catalog):
    b, _, item, factor = catalog
    warehouse = Warehouse(id=uuid4(), business_id=b["business"], name="انبار")
    b["service"].catalog(b["owner"], b["business"], "warehouse", warehouse)
    record = Count(id=uuid4(), business_id=b["business"], warehouse_id=warehouse.id, item_id=item.id,
                   occurred_at=datetime.now(timezone.utc) - timedelta(days=1), quantity="1", unit="pack",
                   evidence=factor.evidence)
    b["service"].propose(b["editor"], b["business"], "past", record)
    with b["db"].transaction(b["viewer"], b["business"]) as c:
        original = c.execute("SELECT * FROM herman.pack_binding_checks WHERE record_id=%s", (record.id,)).fetchone()
    assert original["state"] == "unresolved"
    prefix = f"/businesses/{b['business']}"
    headers = {"Authorization": "Bearer " + b["tokens"][3]}
    with TestClient(create_app(b["db"], b["blob_root"])) as client:
        for path in (f"/catalog/pack-revisions/{factor.id}", f"/catalog/items/{item.id}"):
            response = client.get(prefix + path, headers=headers)
            assert response.status_code == 200 and response.headers["Cache-Control"] == "no-store"
            assert response.json()["historical_usage_status"] == "not_evaluated"
            assert response.json()["explanation_fa"]
        response = client.get(prefix + f"/catalog/items/{item.id}/packs", headers=headers)
        assert response.status_code == 200
        assert response.json()[0]["published"] is True
        assert response.json()[0]["base_quantity"] == "8.000000"
        assert response.json()[0]["historical_usage_status"] == "not_evaluated"
        response = client.get(prefix + f"/pack-bindings/{original['id']}", headers=headers)
        assert response.json()["effective_state"] == "unresolved"
    with b["db"].transaction(b["viewer"], b["business"]) as c:
        assert c.execute("SELECT * FROM herman.pack_binding_checks WHERE record_id=%s", (record.id,)).fetchone() == original


def test_conflicting_alias_rejects_atomically_and_keeps_replacement_slot(catalog):
    b, _, item, factor = catalog
    second = Item(id=uuid4(), business_id=b["business"], sku="SECOND", name_fa="کالای دوم", base_unit="each")
    b["service"].catalog(b["owner"], b["business"], "second", second)
    prefix = f"/businesses/{b['business']}/catalog"
    when = datetime.now(timezone.utc) + timedelta(days=1)
    proposal = dict(id=str(uuid4()), item_id=str(second.id), predecessor_id=str(second.id), sku=item.sku,
                    name_fa="نام جدید", evidence=factor.evidence.model_dump(mode="json"))
    def auth(key):
        return {"Authorization": "Bearer " + b["tokens"][0], "Idempotency-Key": key}

    with TestClient(create_app(b["db"], b["blob_root"])) as client:
        assert client.post(prefix + "/item-revisions", json=proposal, headers=auth("alias-proposal")).status_code == 201
        url = prefix + f"/item-revisions/{proposal['id']}/decision"
        response = client.post(url, json=dict(approved=True, reason_fa="بررسی شد", effective_at=when.isoformat()),
                               headers=auth("alias-conflict"))
        assert response.status_code == 409 and response.headers["Cache-Control"] == "no-store"
        current = client.get(prefix + f"/items/{second.id}", params={"effective_at": when.isoformat()},
                             headers=auth("read")).json()
        assert current["label"]["definition_id"] == str(second.id) and current["label"]["valid_to"] is None
        assert client.post(url, json=dict(approved=False, reason_fa="شناسه با کالای دیگر تداخل دارد"),
                           headers=auth("alias-reject")).status_code == 201
        corrected = dict(proposal, id=str(uuid4()), sku="CORRECTED")
        assert client.post(prefix + "/item-revisions", json=corrected, headers=auth("corrected-proposal")).status_code == 201
        assert client.post(prefix + f"/item-revisions/{corrected['id']}/decision",
                           json=dict(approved=True, reason_fa="شناسهٔ یکتا بررسی شد", effective_at=when.isoformat()),
                           headers=auth("corrected-approved")).status_code == 201
    with b["db"].transaction(b["viewer"], b["business"]) as c:
        assert not c.execute("SELECT 1 FROM herman.idempotency_keys WHERE key='alias-conflict'").fetchone()


@pytest.mark.parametrize("kind", ["item", "pack"])
def test_public_approval_cannot_backdate_a_definition(catalog, kind):
    b, _, item, factor = catalog
    prefix = f"/businesses/{b['business']}/catalog/{kind}-revisions"
    proposal = dict(id=str(uuid4()), item_id=str(item.id),
                    predecessor_id=str(item.id if kind == "item" else factor.id),
                    evidence=factor.evidence.model_dump(mode="json"))
    proposal.update(dict(sku="NEW", name_fa="نام جدید") if kind == "item" else dict(base_quantity="10"))
    def auth(key):
        return {"Authorization": "Bearer " + b["tokens"][0], "Idempotency-Key": key}

    with TestClient(create_app(b["db"], b["blob_root"])) as client:
        assert client.post(prefix, json=proposal, headers=auth("proposal")).status_code == 201
        url = prefix + f"/{proposal['id']}/decision"
        response = client.post(url, json=dict(approved=True, reason_fa="بررسی شد",
            effective_at=(datetime.now(timezone.utc)-timedelta(days=1)).isoformat()), headers=auth("backdated"))
        assert response.status_code == 409 and response.headers["Cache-Control"] == "no-store"
        detail = client.get(prefix + f"/{proposal['id']}", headers=auth("read")).json()
        assert detail["approved"] is None and detail["valid_from"] is None
        assert client.post(url, json=dict(approved=True, reason_fa="از زمان تأیید اعمال شود"),
                           headers=auth("prospective")).status_code == 201
        detail = client.get(prefix + f"/{proposal['id']}", headers=auth("read-again")).json()
        assert datetime.fromisoformat(detail["effective_at"]) >= datetime.fromisoformat(detail["decided_at"])
    with b["db"].transaction(b["viewer"], b["business"]) as c:
        assert not c.execute("SELECT 1 FROM herman.idempotency_keys WHERE key='backdated'").fetchone()
