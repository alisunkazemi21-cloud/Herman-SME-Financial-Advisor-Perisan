from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import model_validator

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
    s = statement
    avg_assets = (s.opening_assets.value + s.total_assets.value) / 2
    avg_equity = (s.opening_equity.value + s.equity.value) / 2
    specs = [
        ("current", "نسبت جاری", s.current_assets.value, s.current_liabilities.value,
         "دارایی جاری / بدهی جاری", ["current_assets", "current_liabilities"]),
        ("quick", "نسبت آنی", s.current_assets.value - s.inventory.value - s.prepayments.value,
         s.current_liabilities.value, "(دارایی جاری − موجودی − پیش‌پرداخت) / بدهی جاری",
         ["current_assets", "inventory", "prepayments", "current_liabilities"]),
        ("equity", "نسبت مالکانه", s.equity.value, s.total_assets.value,
         "حقوق مالکانه / دارایی", ["equity", "total_assets"]),
        ("debt", "نسبت بدهی", s.total_liabilities.value, s.total_assets.value,
         "بدهی / دارایی", ["total_liabilities", "total_assets"]),
        ("gross_margin", "حاشیه سود ناخالص", s.revenue.value - s.cost_of_goods.value, s.revenue.value,
         "(فروش − بهای تمام‌شده) / فروش", ["revenue", "cost_of_goods"]),
        ("net_margin", "حاشیه سود خالص", s.net_income.value, s.revenue.value,
         "سود خالص / فروش", ["net_income", "revenue"]),
        ("roa", "بازده دارایی‌ها", s.net_income.value, avg_assets,
         "سود خالص / متوسط دارایی", ["net_income", "opening_assets", "total_assets"]),
        ("roe", "بازده حقوق صاحبان سهام", s.net_income.value, avg_equity,
         "سود خالص / متوسط حقوق مالکانه", ["net_income", "opening_equity", "equity"]),
        ("turnover", "گردش دارایی‌ها", s.revenue.value, avg_assets,
         "فروش / متوسط دارایی", ["revenue", "opening_assets", "total_assets"]),
        ("interest_coverage", "پوشش بهره", s.ebit.value, s.interest_expense.value,
         "سود قبل از بهره و مالیات / بهره", ["ebit", "interest_expense"]),
    ]
    return [Ratio(key=key, name_fa=name, value=num / den if den > 0 else None, formula_fa=formula,
                  inputs={field: getattr(s, field) for field in fields},
                  warning_fa=None if den > 0 else "مخرج صفر یا منفی است؛ نسبت قابل تفسیر نیست")
            for key, name, num, den, formula, fields in specs]
