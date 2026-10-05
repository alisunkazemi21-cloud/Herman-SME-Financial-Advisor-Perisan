from __future__ import annotations

from src.analytics.ratios import FinancialStatement, compute_ratios
from src.ledger.double_entry import JevLedger


def calculated_context(statement: FinancialStatement) -> dict[str, object]:
    return {"ratios": [ratio.model_dump(mode="json") for ratio in compute_ratios(statement)],
            "period": [str(statement.period_start), str(statement.period_end)]}


def trace_entry(ledger: JevLedger, entry_id: str) -> dict[str, object]:
    return ledger.trace(entry_id)
