"""Duplicate candidates require event context and a human disposition, never amount-only deletion."""
# ruff: noqa: E402
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

psycopg = pytest.importorskip("psycopg")
pytest.importorskip("fastapi")
from fastapi.testclient import TestClient
from test_backend import backend as backend_fixture
from test_backend import database as database_fixture

from src.backend.api import create_app
from src.backend.database import AccessDenied
from src.backend.inventory import Item, Movement
from src.backend.service import Conflict, Warehouse

database = database_fixture
backend = backend_fixture


def prepare(b):
    warehouse = Warehouse(id=uuid4(), business_id=b["business"], name="انبار")
    item = Item(id=uuid4(), business_id=b["business"], sku="MEAT", name_fa="گوشت", base_unit="g")
    b["service"].catalog(b["owner"], b["business"], "warehouse", warehouse)
    b["service"].catalog(b["owner"], b["business"], "item", item)
    document = b["service"].document(b["owner"], b["business"], "doc", "source.csv", "text/csv", b"source")
    return dict(business_id=b["business"], warehouse_id=warehouse.id, item_id=item.id,
        occurred_at=datetime(2026, 9, 1, tzinfo=timezone.utc), quantity="1", unit="kg", kind="purchase",
        evidence=dict(document_id=document, locator="row:2"))


def propose(b, fields, key):
    record = Movement(id=uuid4(), **fields)
    b["service"].propose(b["owner"], b["business"], key, record)
    return record.id


def test_identical_document_bytes_detected_despite_filename_and_tenant_isolation(backend):
    b = backend
    with TestClient(create_app(b["db"], b["blob_root"])) as client:
        headers = {"Authorization": "Bearer " + b["tokens"][0], "X-Filename": "first.csv",
                   "Content-Type": "text/csv", "Idempotency-Key": "first"}
        path = f"/businesses/{b['business']}/documents"
        first = client.post(path, content=b"same-content", headers=headers)
        second = client.post(path, content=b"same-content", headers={**headers, "Idempotency-Key": "second",
                                                                    "X-Filename": "renamed.csv"})
        assert first.status_code == second.status_code == 201
        assert first.json()["duplicate_candidates"]["documents"] == []
        assert second.json()["duplicate_candidates"]["documents"][0]["id"] == first.json()["id"]
        assert first.json()["id"] != second.json()["id"]  # evidence is preserved, not silently removed
    foreign = b["service"].document(b["stranger"], b["other"], "foreign", "foreign.csv", "text/csv", b"same-content")
    assert b["service"].document_duplicates(b["stranger"], b["other"], foreign)["documents"] == []
    with pytest.raises(AccessDenied):
        b["service"].document_duplicates(b["stranger"], b["business"], first.json()["id"])


def test_matching_event_converts_units_and_requires_explicit_review(backend):
    b = backend
    fields = prepare(b)
    first = propose(b, fields, "first")
    second = propose(b, dict(fields, quantity="1000", unit="g"), "second")
    duplicates = b["service"].record(b["owner"], b["business"], second)["duplicate_candidates"]
    assert duplicates["requires_resolution"]
    assert duplicates["records"][0]["id"] == first
    with pytest.raises(Conflict, match="تکرار"):
        b["service"].approve(b["owner"], b["business"], "review", second, True, "بررسی")
    b["service"].approve(b["owner"], b["business"], "review", second, True,
                          "دو خرید مستقل با رسیدهای جدا", duplicate_resolution="distinct_event")
    decision = b["service"].record(b["owner"], b["business"], second)["decision"]
    assert decision["duplicate_resolution"] == "distinct_event"
    b["service"].approve(b["owner"], b["business"], "reject", first, False,
                          "ورود مجدد همان خرید", duplicate_resolution="same_event")
    assert not b["service"].record(b["owner"], b["business"], first)["decision"]["approved"]


def test_equal_quantity_different_time_or_event_is_not_automatically_duplicate(backend):
    b = backend
    fields = prepare(b)
    propose(b, fields, "first")
    later = propose(b, dict(fields, occurred_at=fields["occurred_at"] + timedelta(days=1)), "later")
    waste = propose(b, dict(fields, kind="waste"), "waste")
    for identity in (later, waste):
        result = b["service"].record(b["owner"], b["business"], identity)["duplicate_candidates"]
        assert not result["requires_resolution"]
        b["service"].approve(b["owner"], b["business"], str(identity), identity, True, "رویداد مستقل")


def test_same_event_cannot_be_approved_and_file_duplicate_requires_review(backend):
    b = backend
    fields = prepare(b)
    identity = propose(b, fields, "one")
    b["service"].document(b["owner"], b["business"], "copy", "copy.csv", "text/csv", b"source")
    candidates = b["service"].record(b["owner"], b["business"], identity)["duplicate_candidates"]
    assert candidates["documents"] and not candidates["records"]
    with pytest.raises(ValueError):
        b["service"].approve(b["owner"], b["business"], "bad", identity, True, "تکراری", "same_event")
    with pytest.raises(Conflict):
        b["service"].approve(b["owner"], b["business"], "unreviewed", identity, True, "بدون تصمیم تکرار")
    with TestClient(create_app(b["db"], b["blob_root"])) as client:
        response = client.post(f"/businesses/{b['business']}/records/{identity}/decision",
            headers={"Authorization": "Bearer " + b["tokens"][0], "Idempotency-Key": "reviewed"},
            json={"approved": True, "reason_fa": "نسخه فایل مرجع مشترک، رویداد مستقل است",
                  "duplicate_resolution": "distinct_event"})
        assert response.status_code == 201, response.text
