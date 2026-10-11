"""Shared ratio formulas; callers supply validated, consistently scoped Decimal values."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class RatioDefinition:
    key: str
    name_fa: str
    formula_fa: str
    fields: tuple[str, ...]
    components: Callable[..., tuple[Decimal, Decimal]]

    def calculate(self, values: Mapping[str, Decimal]) -> Decimal | None:
        numerator, denominator = self.components(*(values[name] for name in self.fields))
        return numerator / denominator if denominator > 0 else None


RATIO_DEFINITIONS = (
    RatioDefinition(
        "current",
        "نسبت جاری",
        "دارایی جاری / بدهی جاری",
        ("current_assets", "current_liabilities"),
        lambda assets, liabilities: (assets, liabilities),
    ),
    RatioDefinition(
        "quick",
        "نسبت آنی",
        "(دارایی جاری − موجودی − پیش‌پرداخت) / بدهی جاری",
        ("current_assets", "inventory", "prepayments", "current_liabilities"),
        lambda assets, inventory, prepayments, liabilities: (assets - inventory - prepayments, liabilities),
    ),
    RatioDefinition(
        "equity", "نسبت مالکانه", "حقوق مالکانه / دارایی", ("equity", "total_assets"), lambda e, a: (e, a)
    ),
    RatioDefinition(
        "debt",
        "نسبت بدهی",
        "بدهی / دارایی",
        ("total_liabilities", "total_assets"),
        lambda liabilities, assets: (liabilities, assets),
    ),
    RatioDefinition(
        "gross_margin",
        "حاشیه سود ناخالص",
        "(فروش − بهای تمام‌شده) / فروش",
        ("revenue", "cost_of_goods"),
        lambda r, c: (r - c, r),
    ),
    RatioDefinition(
        "net_margin", "حاشیه سود خالص", "سود خالص / فروش", ("net_income", "revenue"), lambda n, r: (n, r)
    ),
    RatioDefinition(
        "roa",
        "بازده دارایی‌ها",
        "سود خالص / متوسط دارایی",
        ("net_income", "opening_assets", "total_assets"),
        lambda n, o, a: (n, (o + a) / 2),
    ),
    RatioDefinition(
        "roe",
        "بازده حقوق صاحبان سهام",
        "سود خالص / متوسط حقوق مالکانه",
        ("net_income", "opening_equity", "equity"),
        lambda n, o, e: (n, (o + e) / 2),
    ),
    RatioDefinition(
        "turnover",
        "گردش دارایی‌ها",
        "فروش / متوسط دارایی",
        ("revenue", "opening_assets", "total_assets"),
        lambda r, o, a: (r, (o + a) / 2),
    ),
    RatioDefinition(
        "interest_coverage",
        "پوشش بهره",
        "سود قبل از بهره و مالیات / بهره",
        ("ebit", "interest_expense"),
        lambda e, i: (e, i),
    ),
)
