from __future__ import annotations

from src.analytics.benchmarks import BenchmarkRequest, compare
from src.analytics.forecast import MonthlyCashFlow, forecast_cashflow
from src.analytics.ratios import FinancialStatement, compute_ratios
from src.ledger.double_entry import JevLedger


def calculated_context(statement: FinancialStatement, monthly_cashflows: list[MonthlyCashFlow] | None = None,
                       benchmarks: list[BenchmarkRequest] | None = None) -> dict[str, object]:
    return {"ratios": [ratio.model_dump(mode="json") for ratio in compute_ratios(statement)],
            "period": [str(statement.period_start), str(statement.period_end)],
            "forecast": forecast_cashflow(monthly_cashflows or []),
            "benchmarks": [compare(request) for request in benchmarks or []],
            "review_note_fa": "اعداد از ورودی بررسی‌شده هستند؛ هشدار تشخیص و حدود پیش‌بینی باید در توضیح حفظ شوند"}


def trace_entry(ledger: JevLedger, entry_id: str) -> dict[str, object]:
    return ledger.trace(entry_id)
