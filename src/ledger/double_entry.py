from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from filelock import FileLock

from src.ledger.jev import Decision, JevEntry, explain_entry
from src.models import Evidence


def digest(value: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()


class JevLedger:
    """Single-user trusted local ledger; hash chain is tamper-evident, not authentication."""

    def __init__(self, book_path: str | Path) -> None:
        self.path = Path(book_path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = FileLock(str(self.path) + ".lock", timeout=10)

    def _read(self) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        previous = "0" * 64
        proposals: set[str] = set()
        decisions: set[str] = set()
        if not self.path.exists():
            return events
        with self.path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.endswith("\n"):
                    raise ValueError("دفتر ناقص است؛ بازیابی دستی لازم است")
                event = json.loads(line)
                stored = event.pop("hash")
                if event["previous"] != previous or digest(event) != stored:
                    raise ValueError("زنجیره دفتر تغییر کرده است")
                if event["sequence"] != len(events) + 1:
                    raise ValueError("ترتیب رویداد نامعتبر است")
                if event["kind"] == "proposal":
                    entry = JevEntry.model_validate(event["payload"])
                    if entry.jev_id in proposals:
                        raise ValueError("سند تکراری در دفتر")
                    proposals.add(entry.jev_id)
                elif event["kind"] == "decision":
                    decision = Decision.model_validate(event["payload"])
                    if decision.jev_id not in proposals or decision.jev_id in decisions:
                        raise ValueError("تصمیم نامعتبر در دفتر")
                    decisions.add(decision.jev_id)
                else:
                    raise ValueError("نوع رویداد ناشناخته")
                event["hash"] = stored
                events.append(event)
                previous = stored
        return events

    def events(self) -> list[dict[str, Any]]:
        with self.lock:
            return self._read()

    def _append(self, kind: str, payload: dict[str, Any], events: list[dict[str, Any]]) -> None:
        event = {"sequence": len(events) + 1, "kind": kind, "payload": payload,
                 "timestamp": datetime.now(timezone.utc).isoformat(),
                 "previous": events[-1]["hash"] if events else "0" * 64}
        event["hash"] = digest(event)
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def add_entry(self, entry: JevEntry) -> str:
        entry = JevEntry.model_validate(entry.model_dump())
        with self.lock:
            events = self._read()
            proposals = {e["payload"]["jev_id"]: e["payload"] for e in events if e["kind"] == "proposal"}
            if entry.jev_id in proposals:
                raise ValueError("شناسه سند تکراری است")
            if entry.reversal_of:
                original = proposals.get(entry.reversal_of)
                approved = any(e["kind"] == "decision" and e["payload"]["jev_id"] == entry.reversal_of
                               and e["payload"]["approved"] for e in events)
                if not original or not approved:
                    raise ValueError("فقط سند تأییدشده قابل برگشت است")
                if any(p.get("reversal_of") == entry.reversal_of for p in proposals.values()):
                    raise ValueError("برگشت تکراری مجاز نیست")
                if (entry.debit_account != original["credit_account"] or
                        entry.credit_account != original["debit_account"] or
                        entry.amount != Decimal(original["amount"])):
                    raise ValueError("سند برگشت باید دقیقاً معکوس اصل باشد")
            entry.evidence.verify()
            store = self.path.parent / "evidence"
            store.mkdir(exist_ok=True)
            archived = store / entry.evidence.sha256
            content = Path(entry.evidence.source_file).read_bytes()
            if hashlib.sha256(content).hexdigest() != entry.evidence.sha256:
                raise ValueError("شاهد حین خواندن تغییر کرده است")
            if not archived.exists():
                with archived.open("xb") as handle:
                    handle.write(content)
                    handle.flush()
                    os.fsync(handle.fileno())
            evidence = Evidence(sha256=entry.evidence.sha256, source_file=str(archived),
                                locator=entry.evidence.locator)
            evidence.verify()
            payload = entry.model_dump(mode="json")
            payload["evidence"] = evidence.model_dump(mode="json")
            self._append("proposal", payload, events)
        return entry.jev_id

    def decide(self, decision: Decision) -> None:
        decision = Decision.model_validate(decision.model_dump())
        with self.lock:
            events = self._read()
            matching = [e for e in events if e["payload"]["jev_id"] == decision.jev_id]
            if not matching or any(e["kind"] == "decision" for e in matching):
                raise ValueError("سند وجود ندارد یا قبلاً تصمیم‌گیری شده است")
            JevEntry.model_validate(matching[0]["payload"]).evidence.verify()
            self._append("decision", decision.model_dump(mode="json"), events)

    def approved_entries(self) -> list[JevEntry]:
        events = self.events()
        approved = {e["payload"]["jev_id"] for e in events
                    if e["kind"] == "decision" and e["payload"]["approved"]}
        entries = [JevEntry.model_validate(e["payload"]) for e in events
                   if e["kind"] == "proposal" and e["payload"]["jev_id"] in approved]
        for entry in entries:
            entry.evidence.verify()
        return entries

    def balances(self) -> dict[str, Decimal]:
        balances: dict[str, Decimal] = {}
        for entry in self.approved_entries():
            balances[entry.debit_account] = balances.get(entry.debit_account, Decimal(0)) + entry.amount
            balances[entry.credit_account] = balances.get(entry.credit_account, Decimal(0)) - entry.amount
        return balances

    def trace(self, entry_id: str) -> dict[str, Any]:
        events = [e for e in self.events() if e["payload"]["jev_id"] == entry_id]
        if not events:
            raise KeyError(entry_id)
        evidence = Evidence.model_validate(events[0]["payload"]["evidence"])
        evidence.verify()
        status = "در انتظار بررسی" if len(events) == 1 else (
            "تأییدشده" if events[-1]["payload"]["approved"] else "ردشده")
        return {"evidence": evidence.model_dump(), "events": events, "status_fa": status,
                "explanation_fa": explain_entry(JevEntry.model_validate(events[0]["payload"]), status)}
