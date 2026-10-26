"""Duplicate quantities require each record's own supported interpretation."""

from uuid import uuid4

import pytest
from test_backend import backend as backend_fixture
from test_backend import database as database_fixture
from test_pack_bindings import pending as pending_fixture
from test_pack_bindings import review_value

from src.backend import duplicates
from src.backend.inventory import Count
from src.backend.pack_binding_selection import SelectionLimit

backend = backend_fixture
database = database_fixture
pending = pending_fixture


def candidates(b, identity):
    return b["service"].record(b["viewer"], b["business"], identity)["duplicate_candidates"]["records"]


def test_equal_raw_packs_and_late_baseline_do_not_make_a_numeric_match(pending):
    b, bindings, first, check, factor, documents = pending
    second = first.model_copy(update={"id": uuid4()})
    base = Count.model_validate(dict(first.model_dump(), id=uuid4(), unit="each", quantity="8"))
    for key, record in (("second", second), ("base", base)):
        b["service"].propose(b["editor"], b["business"], key, record)
    assert candidates(b, first.id) == candidates(b, second.id) == candidates(b, base.id) == []
    bindings.resolve(b["owner"], b["business"], "resolve", check, review_value(factor, documents))
    assert {row["id"] for row in candidates(b, base.id)} == {first.id}
    assert {row["id"] for row in candidates(b, first.id)} == {base.id}
    assert candidates(b, second.id) == []
    with b["db"].transaction(b["viewer"], b["business"]) as c:
        assert c.execute("SELECT state FROM herman.pack_binding_checks WHERE record_id=%s",
                         (second.id,)).fetchone()["state"] == "unresolved"


@pytest.mark.parametrize("limit", ["MAX_DUPLICATE_ROWS", "MAX_DUPLICATE_BYTES"])
def test_incomplete_comparison_budget_blocks_approval_atomically(pending, monkeypatch, limit):
    b, _, record, _, _, _ = pending
    monkeypatch.setattr(duplicates, limit, 1)
    with pytest.raises(SelectionLimit):
        b["service"].approve(b["owner"], b["business"], "limited-approval", record.id, True, "بررسی شد")
    with b["db"].transaction(b["viewer"], b["business"]) as c:
        assert not c.execute("SELECT 1 FROM herman.approvals WHERE record_id=%s", (record.id,)).fetchone()
        assert not c.execute("SELECT 1 FROM herman.idempotency_keys WHERE key='limited-approval'").fetchone()


def test_final_encoded_binding_envelope_is_bounded(pending, monkeypatch):
    b, bindings, record, check, factor, documents = pending
    bindings.resolve(b["owner"], b["business"], "resolve", check, review_value(factor, documents))
    sizes = dict(raw=0, final=0)
    original = duplicates.json.dumps

    def observed(value, *args, **kwargs):
        encoded = original(value, *args, **kwargs)
        if isinstance(value, list):
            sizes["raw"] += len(encoded.encode())
        elif isinstance(value, dict) and "pack_bindings" in value:
            sizes["final"] = len(encoded.encode())
        return encoded

    with monkeypatch.context() as patch:
        patch.setattr(duplicates.json, "dumps", observed)
        assert candidates(b, record.id) == []
    assert sizes["final"] > sizes["raw"]
    monkeypatch.setattr(duplicates, "MAX_DUPLICATE_BYTES", sizes["final"] - 1)
    with pytest.raises(SelectionLimit):
        candidates(b, record.id)
