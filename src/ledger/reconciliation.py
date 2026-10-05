from __future__ import annotations

from datetime import date

from src.models import Evidence, Model, Money


class BankRow(Model):
    row_id: str
    entry_date: date
    amount: Money
    evidence: Evidence


def reconcile(bank: list[BankRow], book: list[BankRow]) -> dict[str, object]:
    """Conservative one-to-one matching: ambiguous duplicates remain for review."""
    if len({r.row_id for r in bank}) != len(bank) or len({r.row_id for r in book}) != len(book):
        raise ValueError("شناسه ردیف تکراری است")
    matches: list[tuple[str, str]] = []
    for row in bank:
        candidates = [b for b in book if (b.entry_date, b.amount) == (row.entry_date, row.amount)]
        same = [b for b in bank if (b.entry_date, b.amount) == (row.entry_date, row.amount)]
        if len(candidates) == len(same) == 1:
            matches.append((row.row_id, candidates[0].row_id))
    return {"matches": matches, "unmatched_bank": [r.row_id for r in bank if r.row_id not in
            {m[0] for m in matches}], "unmatched_book": [r.row_id for r in book if r.row_id not in
            {m[1] for m in matches}], "note_fa": "تطبیق پیشنهادی است؛ ثبت خودکار انجام نمی‌شود"}
