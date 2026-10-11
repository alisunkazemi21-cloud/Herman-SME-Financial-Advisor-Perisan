from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import model_validator

from src.analytics.ratio_definitions import RATIO_DEFINITIONS
from src.models import Fact, Model, Money, exact_decimal


class FinancialStatement(Model):
    period_start: date
    period_end: date
    currency: Literal["IRR"] = "IRR"
    current_assets: Fact
    inventory: Fact
    prepayments: Fact
    current_liabilities: Fact
    total_assets: Fact
    total_liabilities: Fact
    equity: Fact
    opening_assets: Fact
    opening_equity: Fact
    revenue: Fact
    cost_of_goods: Fact
    net_income: Fact
    ebit: Fact
    interest_expense: Fact

    @model_validator(mode="after")
    def consistent(self) -> FinancialStatement:
        if self.period_start >= self.period_end:
            raise ValueError("پایان دوره باید پس از شروع باشد")
        for name in ("current_assets", "inventory", "prepayments", "current_liabilities", "total_assets",
                     "total_liabilities", "opening_assets", "revenue", "cost_of_goods", "interest_expense"):
            if getattr(self, name).value < 0:
                raise ValueError("مقدار این قلم نباید منفی باشد: " + name)
        if self.total_assets.value != self.total_liabilities.value + self.equity.value:
            raise ValueError("معادله دارایی = بدهی + حقوق مالکانه برقرار نیست")
        if self.current_assets.value > self.total_assets.value:
            raise ValueError("دارایی جاری بیشتر از کل دارایی است")
        if self.current_liabilities.value > self.total_liabilities.value:
            raise ValueError("بدهی جاری بیشتر از کل بدهی است")
        if self.inventory.value + self.prepayments.value > self.current_assets.value:
            raise ValueError("موجودی و پیش‌پرداخت بیشتر از دارایی جاری است")
        return self


class Ratio(Model):
    key: str
    name_fa: str
    value: Money | None
    formula_fa: str
    inputs: dict[str, Fact]
    warning_fa: str | None = None


def current_ratio_fa(current_assets: Money, current_liabilities: Money) -> Decimal | None:
    assets, liabilities = exact_decimal(current_assets), exact_decimal(current_liabilities)
    return assets / liabilities if liabilities > 0 else None


def compute_ratios(statement: FinancialStatement) -> list[Ratio]:
    result = []
    for definition in RATIO_DEFINITIONS:
        inputs = {field: getattr(statement, field) for field in definition.fields}
        value = definition.calculate({field: fact.value for field, fact in inputs.items()})
        result.append(Ratio(key=definition.key, name_fa=definition.name_fa, value=value,
                            formula_fa=definition.formula_fa, inputs=inputs,
                            warning_fa=None if value is not None else "مخرج صفر یا منفی است؛ نسبت قابل تفسیر نیست"))
    return result
