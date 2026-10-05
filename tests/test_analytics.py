from datetime import date

import pytest

from src.analytics.cashflow import CashFlow, calculate_xirr, summarize
from src.analytics.forecast import analyze_cashflow_stationarity, forecast_cashflow
from src.ledger.reconciliation import BankRow, reconcile


def test_forecast_intervals_and_reproducibility(demo):
    result = forecast_cashflow(demo.monthly_cashflows)
    assert result == forecast_cashflow(demo.monthly_cashflows)
    assert len(result["predictions"]) == 3
    assert result["predictions"][0]["month"] == "1405/01"
    for prediction in result["predictions"]:
        assert prediction["lower"] <= prediction["estimate"] <= prediction["upper"]


def test_forecast_insufficient_and_nonfinite(demo):
    assert forecast_cashflow(demo.monthly_cashflows[:8])["predictions"] == []
    assert analyze_cashflow_stationarity([1.0] * 36)["is_stationary"] is None
    with pytest.raises(ValueError):
        analyze_cashflow_stationarity([float("nan")] * 24)
    with pytest.raises(ValueError):
        forecast_cashflow(demo.monthly_cashflows[::2])


def test_xirr_and_cashflow(evidence):
    flows = [CashFlow(entry_date=date(2025, 1, 1), amount=-100, category="investing", evidence=evidence),
             CashFlow(entry_date=date(2026, 1, 1), amount=110, category="operating", evidence=evidence)]
    assert calculate_xirr(flows)["value"] == pytest.approx(0.1)
    assert summarize(flows)["net"] == 10
    with pytest.raises(ValueError):
        calculate_xirr(flows[:1])


def test_reconciliation_ambiguous_duplicates(evidence):
    def row(key):
        return BankRow(row_id=key, entry_date=date(2026, 1, 1), amount=100, evidence=evidence)
    assert reconcile([row("b")], [row("l")])["matches"] == [("b", "l")]
    assert reconcile([row("b1"), row("b2")], [row("l")])["matches"] == []


def test_benchmark_rates_units_and_provenance(evidence):
    from src.analytics.benchmarks import BenchmarkRequest, Quote, compare
    from src.models import Fact
    request = BenchmarkRequest(amount_irr=Fact(value=1000, evidence=evidence),
        start=Quote(day="2025-01-01", asset="USD", irr_per_unit=Fact(value=100, evidence=evidence)),
        end=Quote(day="2026-01-01", asset="USD", irr_per_unit=Fact(value=120, evidence=evidence)))
    result = compare(request)
    assert result["units"] == "10" and result["ending_value_irr"] == "1200"
    assert result["nominal_return"] == "0.2" and len(result["evidence"]) == 3
    bad = request.model_dump()
    bad["end"]["asset"] = "GOLD_18K_GRAM"
    with pytest.raises(ValueError):
        compare(BenchmarkRequest.model_validate(bad))


@pytest.mark.parametrize("field,value", [("current_assets", -1), ("current_assets", 600000000),
    ("current_liabilities", 300000000), ("inventory", 300000000)])
def test_statement_inconsistent_components(demo, field, value):
    from src.analytics.ratios import FinancialStatement
    data = demo.statement.model_dump()
    data[field]["value"] = value
    with pytest.raises(ValueError):
        FinancialStatement.model_validate(data)


def test_statement_invalid_period(demo):
    from src.analytics.ratios import FinancialStatement
    data = demo.statement.model_dump()
    data["period_start"] = data["period_end"]
    with pytest.raises(ValueError):
        FinancialStatement.model_validate(data)
