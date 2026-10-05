from decimal import Decimal

import pytest

from src.analytics.ratios import FinancialStatement, compute_ratios, current_ratio_fa


def test_all_ten_ratios_against_independent_expected_values(demo):
    result = {r.key: r.value for r in compute_ratios(demo.statement)}
    expected = {"current": Decimal(2), "quick": Decimal("1.4"), "equity": Decimal("0.6"),
                "debt": Decimal("0.4"), "gross_margin": Decimal("0.4"), "net_margin": Decimal("0.1"),
                "roa": Decimal(60) / 450, "roe": Decimal(60) / 275,
                "turnover": Decimal(600) / 450, "interest_coverage": Decimal(9)}
    assert result == expected
    assert all(r.inputs for r in compute_ratios(demo.statement))


def test_zero_and_negative_denominators():
    assert current_ratio_fa(200_000_000, 100_000_000) == 2
    assert current_ratio_fa(1, 0) is None
    assert current_ratio_fa(1, -1) is None
    with pytest.raises(ValueError):
        current_ratio_fa(0.1, 1)


def test_unbalanced_statement_rejected(demo):
    payload = demo.statement.model_dump()
    payload["equity"]["value"] = "1"
    with pytest.raises(ValueError):
        FinancialStatement.model_validate(payload)


def test_undefined_ratios_have_explanation(demo):
    payload = demo.statement.model_dump()
    payload["interest_expense"]["value"] = "0"
    ratio = compute_ratios(FinancialStatement.model_validate(payload))[-1]
    assert ratio.value is None and ratio.warning_fa
