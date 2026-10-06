"""Extraction-to-proposal checkpoint: transactions, provenance, and human review."""
# ruff: noqa: E402
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from pydantic import ValidationError

psycopg = pytest.importorskip("psycopg")
pytest.importorskip("fastapi")
from fastapi.testclient import TestClient
from test_backend import backend as backend_fixture
from test_backend import database as database_fixture
from test_backend import seed_inventory
from test_inventory import inventory_payload as inventory_fixture

from src.backend.api import create_app
from src.backend.database import AccessDenied
from src.backend.imports import TabularImport, TabularImporter
from src.backend.inventory import Item
from src.backend.jobs import ExtractionInput, ExtractionQueue
from src.backend.service import Conflict, NotFound, Warehouse
from src.backend.worker import process_one

database = database_fixture
backend = backend_fixture
inventory_payload = inventory_fixture


def source(b, content="sku,quantity,unit,time\nMEAT,۵,kg,2026-09-01T00:00:00+03:30\n", key="csv"):
    document_id = b["service"].document(b["owner"], b["business"], key, "inventory.csv", "text/csv", content.encode())
    queue = ExtractionQueue(b["service"])
    job_id = queue.enqueue(b["owner"], b["business"], key + ":job", ExtractionInput(document_id=document_id))
    process_one(queue, b["tokens"][0], b["business"])
    job = queue.read(b["owner"], b["business"], job_id)
    assert job["status"] == "succeeded", job
    return job["extraction"]["id"]


def setup_import(b, content=None):
    warehouse = Warehouse(id=uuid4(), business_id=b["business"], name="انبار")
    item = Item(id=uuid4(), business_id=b["business"], sku="MEAT", name_fa="گوشت", base_unit="g")
    b["service"].catalog(b["owner"], b["business"], "warehouse", warehouse)
    b["service"].catalog(b["owner"], b["business"], "item", item)
    extraction = source(b) if content is None else source(b, content)
    mapping = TabularImport(extraction_id=extraction, sheet="CSV", rows=[2], record_kind="movement",
        warehouse_id=warehouse.id, sku_column="sku", quantity_column="quantity", unit_column="unit",
        time_column="time", movement_kind="purchase")
    return TabularImporter(b["service"]), mapping


def test_import_proposal_review_and_provenance(backend):
    b = backend
    importer, mapping = setup_import(b)
    with TestClient(create_app(b["db"], b["blob_root"])) as client:
        headers = {"Authorization": "Bearer " + b["tokens"][2], "Idempotency-Key": "import"}
        response = client.post(f"/businesses/{b['business']}/tabular-imports", headers=headers,
                               json=mapping.model_dump(mode="json"))
        assert response.status_code == 201, response.text
    record_id = response.json()["records"][0]["id"]
    record = b["service"].record(b["owner"], b["business"], record_id)
    assert record["decision"] is None
    assert record["detail"]["quantity"] == 5
    assert record["origin"]["extraction_id"] == mapping.extraction_id
    assert record["origin"]["source_values"]["quantity"] == "5"
    assert record["origin"]["mapping"]["sku_column"] == "sku"
    with pytest.raises(AccessDenied):
        b["service"].approve(b["editor"], b["business"], "approve", record_id, True, "بررسی")
    b["service"].approve(b["owner"], b["business"], "approve", record_id, True, "بررسی")
    assert b["service"].record(b["owner"], b["business"], record_id)["decision"]["approved"]


def test_one_bad_row_rolls_back_whole_batch(backend):
    b = backend
    importer, mapping = setup_import(b, "sku,quantity,unit,time\nMEAT,5,kg,2026-09-01T00:00:00Z\n"
                                       "UNKNOWN,8,kg,2026-09-01T00:00:00Z\n")
    mapping = mapping.model_copy(update={"rows": (2, 3)})
    with pytest.raises(ValueError, match="SKU"):
        importer.create(b["owner"], b["business"], "import", mapping)
    with b["db"].transaction(b["owner"], b["business"]) as c:
        for table in ("records", "stock_movements", "record_sources", "import_batches"):
            assert c.execute(f"SELECT count(*) AS n FROM herman.{table}").fetchone()["n"] == 0
        assert not c.execute("SELECT 1 FROM herman.idempotency_keys WHERE key='import'").fetchone()


def test_duplicate_row_blocked_across_requests_and_extraction_versions(backend):
    b = backend
    importer, mapping = setup_import(b)
    identity = importer.create(b["owner"], b["business"], "import", mapping)
    assert importer.create(b["owner"], b["business"], "import", mapping) == identity
    with pytest.raises(Conflict):
        importer.create(b["owner"], b["business"], "another-key", mapping)
    with b["db"].transaction(b["owner"], b["business"]) as c:
        document_id = c.execute("SELECT document_id FROM herman.record_sources").fetchone()["document_id"]
    queue = ExtractionQueue(b["service"])
    second_job = queue.enqueue(b["owner"], b["business"], "extract-again", ExtractionInput(document_id=document_id))
    process_one(queue, b["tokens"][0], b["business"])
    second_extraction = queue.read(b["owner"], b["business"], second_job)["extraction"]["id"]
    with pytest.raises(Conflict):
        importer.create(b["owner"], b["business"], "new-version",
                        mapping.model_copy(update={"extraction_id": second_extraction}))


def test_concurrent_idempotent_import(backend):
    b = backend
    importer, mapping = setup_import(b)
    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(pool.map(lambda _: importer.create(b["owner"], b["business"], "same-key", mapping), range(4)))
    assert len(set(ids)) == 1
    assert len(importer.read(b["owner"], b["business"], ids[0])["records"]) == 1


def test_repeated_rows_inside_one_file_are_reviewed_before_approval(backend):
    b = backend
    importer, mapping = setup_import(b, "sku,quantity,unit,time\nMEAT,5,kg,2026-09-01T00:00:00Z\n"
                                       "MEAT,5000,g,2026-09-01T00:00:00Z\n")
    mapping = mapping.model_copy(update={"rows": (2, 3)})
    identity = importer.create(b["owner"], b["business"], "rows", mapping)
    rows = importer.read(b["owner"], b["business"], identity)["records"]
    assert all(row["duplicate_candidates"]["requires_resolution"] for row in rows)
    b["service"].approve(b["owner"], b["business"], "reject-copy", rows[1]["id"], False,
                          "ردیف دوم تکرار همان خرید است", "same_event")
    b["service"].approve(b["owner"], b["business"], "accept-original", rows[0]["id"], True,
                          "ردیف اصلی پس از رد ردیف تکراری")


@pytest.mark.parametrize("change", ["time", "unit", "duplicate_rows", "kind"])
def test_mapping_does_not_guess_missing_semantics(backend, change):
    b = backend
    _, mapping = setup_import(b)
    payload = mapping.model_dump(mode="json")
    if change == "time":
        payload["time_column"] = None
    elif change == "unit":
        payload["unit"] = "g"
    elif change == "duplicate_rows":
        payload["rows"] = [2, 2]
    else:
        payload["movement_kind"] = None
    with pytest.raises(ValidationError):
        TabularImport.model_validate(payload)


def test_cross_tenant_extraction_rejected(backend):
    b = backend
    importer, mapping = setup_import(b)
    with pytest.raises(NotFound):
        importer.create(b["stranger"], b["other"], "steal", mapping)
    with pytest.raises(AccessDenied):
        importer.create(b["viewer"], b["business"], "viewer", mapping)


def test_imported_movement_provenance_saved_in_analysis(backend, inventory_payload):
    b = backend
    analysis_input = seed_inventory(b, inventory_payload)
    extraction = source(b)
    mapping = TabularImport(extraction_id=extraction, sheet="CSV", rows=[2], record_kind="movement",
        warehouse_id=analysis_input.scope.warehouse_id, sku_column="sku", quantity_column="quantity",
        unit_column="unit", time_column="time", movement_kind="purchase")
    importer = TabularImporter(b["service"])
    batch = importer.create(b["owner"], b["business"], "import", mapping)
    record_id = importer.read(b["owner"], b["business"], batch)["records"][0]["id"]
    before = b["service"].analyze(b["owner"], b["business"], "before-review", analysis_input)
    assert b["service"].analysis(b["owner"], b["business"], before)["result"]["status"] == "incomplete"
    b["service"].approve(b["owner"], b["business"], "review-import", record_id, True, "بررسی خرید")
    after = b["service"].analyze(b["owner"], b["business"], "after-review", analysis_input)
    result = b["service"].analysis(b["owner"], b["business"], after)
    assert result["result"]["status"] == "complete"
    assert float(result["result"]["unexplained_shortage"]) == 12000  # original 7 kg + reviewed 5 kg purchase
    assert result["source_provenance"][0]["extraction_id"] == str(extraction)
    assert result["source_provenance"][0]["source_row"] == 2
