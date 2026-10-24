from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from test_backend import backend as backend_fixture
from test_backend import database as database_fixture
from test_tabular_imports import setup_import, source

from src.backend.catalog import Catalog, ItemDecision, ItemProposal
from src.backend.inventory import EvidenceRef
from src.backend.item_selection import resolve_sku
from src.backend.service import Conflict

backend = backend_fixture
database = database_fixture


def rename(b, cat, item, document, when):
    value = ItemProposal(id=uuid4(), item_id=item, predecessor_id=item, sku="BEEF", name_fa="گوشت گاو",
                         evidence=EvidenceRef(document_id=document, locator="CSV:row:2"))
    cat.propose_item(b["editor"], b["business"], "rename", value)
    cat.decide_item(b["owner"], b["business"], "review-rename", value.id,
                    ItemDecision(approved=True, reason_fa="بررسی نام و کد", effective_at=when))
    return value


def test_dated_import_retains_original_alias_and_definition(backend):
    b = backend
    importer, mapping = setup_import(b)
    original_batch = importer.create(b["owner"], b["business"], "original-import", mapping)
    with b["db"].transaction(b["owner"], b["business"]) as c:
        original = c.execute("SELECT * FROM herman.record_sources WHERE batch_id=%s", (original_batch,)).fetchone()
        item = c.execute("SELECT id FROM herman.items WHERE sku='MEAT'").fetchone()["id"]
    assert original["item_definition_id"] == item
    activation = datetime.now(timezone.utc) + timedelta(days=1)
    cat = Catalog(b["service"])
    value = rename(b, cat, item, original["document_id"], activation)
    with b["db"].transaction(b["owner"], b["business"]) as c:
        assert c.execute("SELECT * FROM herman.record_sources WHERE batch_id=%s", (original_batch,)).fetchone() == original
        assert c.execute("SELECT sku,name_fa FROM herman.items WHERE id=%s", (item,)).fetchone() == {
            "sku": "MEAT", "name_fa": "گوشت"}
        assert resolve_sku(c, b["business"], "MEAT", activation-timedelta(microseconds=1))["definition_id"] == item
        assert resolve_sku(c, b["business"], "BEEF", activation)["definition_id"] == value.id
        with pytest.raises(ValueError, match="SKU"):
            resolve_sku(c, b["business"], "MEAT", activation)
    before = (activation-timedelta(microseconds=1)).isoformat()
    after = activation.isoformat()
    extraction = source(b, f"sku,quantity,unit,time\nMEAT,1,kg,{before}\nBEEF,2,kg,{after}\n", "dated")
    dated = mapping.model_copy(update={"extraction_id": extraction, "rows": (2, 3)})
    batch = importer.create(b["owner"], b["business"], "dated-import", dated)
    assert importer.create(b["owner"], b["business"], "dated-import", dated) == batch
    with b["db"].transaction(b["owner"], b["business"]) as c:
        rows = c.execute("SELECT item_definition_id,source_values FROM herman.record_sources "
                         "WHERE batch_id=%s ORDER BY source_row", (batch,)).fetchall()
    assert [row["item_definition_id"] for row in rows] == [item, value.id]
    assert [row["source_values"]["sku"] for row in rows] == ["MEAT", "BEEF"]
    wrong = source(b, f"sku,quantity,unit,time\nMEAT,1,kg,{after}\n", "retired")
    with pytest.raises(ValueError, match="SKU"):
        importer.create(b["owner"], b["business"], "retired-import",
                        mapping.model_copy(update={"extraction_id": wrong}))
    with b["db"].transaction(b["owner"], b["business"]) as c:
        assert c.execute("SELECT count(*) AS n FROM herman.import_batches").fetchone()["n"] == 2
        assert c.execute("SELECT count(*) AS n FROM herman.record_sources").fetchone()["n"] == 3
    assert len(cat.item_history(b["viewer"], b["business"], item)) == 2


def test_item_source_tamper_blocks_approval_but_allows_rejection(backend):
    b = backend
    importer, mapping = setup_import(b)
    importer.create(b["owner"], b["business"], "initial", mapping)
    with b["db"].transaction(b["owner"], b["business"]) as c:
        item = c.execute("SELECT id FROM herman.items").fetchone()["id"]
        document = c.execute("SELECT * FROM herman.documents").fetchone()
    cat = Catalog(b["service"])
    value = ItemProposal(id=uuid4(), item_id=item, predecessor_id=item, sku="BEEF", name_fa="گوشت گاو",
                         evidence=EvidenceRef(document_id=document["id"], locator="CSV:row:2"))
    cat.propose_item(b["editor"], b["business"], "p", value)
    path = b["blob_root"] / str(b["business"]) / document["sha256"]
    path.write_bytes(b"changed")
    with pytest.raises(Conflict):
        cat.decide_item(b["owner"], b["business"], "a", value.id,
                        ItemDecision(approved=True, reason_fa="بررسی"))
    cat.decide_item(b["owner"], b["business"], "reject", value.id,
                    ItemDecision(approved=False, reason_fa="شاهد تغییر کرده است"))
    with b["db"].transaction(b["owner"], b["business"]) as c:
        assert resolve_sku(c, b["business"], "MEAT", datetime.now(timezone.utc))["definition_id"] == item
