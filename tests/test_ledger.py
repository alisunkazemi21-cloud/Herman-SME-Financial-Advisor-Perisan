import json
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.ledger.double_entry import JevLedger
from src.ledger.jev import Decision, JevEntry


def approve(ledger, entry_id="J1"):
    ledger.decide(Decision(jev_id=entry_id, actor="human:owner", approved=True,
                          reviewed_values=True, reason_fa="مبلغ و شاهد بررسی شد"))


def test_proposal_not_posted_until_human_approval(tmp_path, entry):
    ledger = JevLedger(tmp_path / "book.jsonl")
    ledger.add_entry(entry)
    assert ledger.balances() == {}
    before = ledger.path.read_bytes()
    approve(ledger)
    assert ledger.path.read_bytes().startswith(before)
    assert ledger.balances() == {"1000": Decimal(1000), "4000": Decimal(-1000)}
    assert sum(ledger.balances().values()) == 0
    assert ledger.trace("J1")["status_fa"] == "تأییدشده"


@pytest.mark.parametrize("changes", [{"amount": 0}, {"amount": -1}, {"amount": 0.1},
    {"amount": "NaN"}, {"approved": True}, {"debit_account": "bad"},
    {"credit_account": "1000"}, {"jalali_date": "1405/01/02"}, {"evidence_ref": "wrong"}])
def test_invalid_entry(entry, changes):
    with pytest.raises((ValueError, ValidationError)):
        JevEntry.model_validate({**entry.model_dump(), **changes})


def test_agent_cannot_approve():
    with pytest.raises(ValidationError):
        Decision(jev_id="J1", actor="agent:analyst", approved=True,
                 reviewed_values=True, reason_fa="بررسی شد")


def test_duplicate_and_tamper(tmp_path, entry):
    ledger = JevLedger(tmp_path / "book.jsonl")
    ledger.add_entry(entry)
    with pytest.raises(ValueError):
        ledger.add_entry(entry)
    row = json.loads(ledger.path.read_text(encoding="utf-8"))
    row["payload"]["amount"] = "2000"
    ledger.path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="زنجیره"):
        ledger.events()


def test_reversal_is_new_approved_entry(tmp_path, entry):
    ledger = JevLedger(tmp_path / "book.jsonl")
    ledger.add_entry(entry)
    approve(ledger)
    reverse = JevEntry.model_validate({**entry.model_dump(), "jev_id": "R1", "reversal_of": "J1",
                                      "debit_account": "4000", "credit_account": "1000"})
    ledger.add_entry(reverse)
    assert ledger.balances()["1000"] == 1000
    approve(ledger, "R1")
    assert all(v == 0 for v in ledger.balances().values())
    with pytest.raises(ValueError):
        approve(ledger)


def test_evidence_archived_and_verified(tmp_path, entry):
    ledger = JevLedger(tmp_path / "book.jsonl")
    ledger.add_entry(entry)
    from pathlib import Path
    Path(entry.evidence.source_file).write_text("changed")
    assert ledger.trace("J1")["evidence"]["sha256"] == entry.evidence.sha256
    Path(ledger.trace("J1")["evidence"]["source_file"]).write_text("tamper")
    with pytest.raises(ValueError):
        approve(ledger)


def test_concurrent_appends(tmp_path, entry):
    path = tmp_path / "book.jsonl"
    def add(number):
        JevLedger(path).add_entry(JevEntry.model_validate({**entry.model_dump(), "jev_id": str(number)}))
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(add, range(12)))
    assert len(JevLedger(path).events()) == 12


def test_partial_write_fails_closed(tmp_path, entry):
    ledger = JevLedger(tmp_path / "book.jsonl")
    ledger.add_entry(entry)
    with ledger.path.open("a") as handle:
        handle.write('{"incomplete":')
    with pytest.raises(ValueError):
        ledger.events()
