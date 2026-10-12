"""Request-only financial figures and calculations; no storage or retrieval capabilities."""

from __future__ import annotations

import hashlib
from datetime import date
from decimal import Context, Decimal, localcontext
from functools import partial
from typing import Annotated, Literal, get_args

from pydantic import BeforeValidator, Field, StringConstraints, field_validator, model_validator

from src.analytics.ratio_definitions import RATIO_DEFINITIONS
from src.backend.quick_document_models import QuickOrigin
from src.models import Model, Money, decimal_precision

SourceId = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")]
Amount = Annotated[
    Money,
    Field(max_digits=28, decimal_places=6),
    BeforeValidator(partial(decimal_precision, digits=28, places=6)),
]
FinancialField = Literal[
    "current_assets",
    "inventory",
    "prepayments",
    "current_liabilities",
    "total_assets",
    "total_liabilities",
    "equity",
    "opening_assets",
    "opening_equity",
    "revenue",
    "cost_of_goods",
    "net_income",
    "ebit",
    "interest_expense",
    "opening_cash",
    "cash_inflows",
    "cash_outflows",
]
MetricKey = Literal[
    "current",
    "quick",
    "equity",
    "debt",
    "gross_margin",
    "net_margin",
    "roa",
    "roe",
    "turnover",
    "interest_coverage",
    "net_cash_flow",
    "closing_cash",
]
NONNEGATIVE = set(get_args(FinancialField)) - {
    "equity",
    "opening_equity",
    "net_income",
    "ebit",
    "opening_cash",
}


class QuickSource(Model):
    source_id: SourceId
    title_fa: str = Field(min_length=1, max_length=160)
    text_fa: Annotated[str, StringConstraints(strip_whitespace=False, min_length=1, max_length=6000)]
    origin: QuickOrigin | None = None

    @field_validator("text_fa")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("متن منبع نباید خالی باشد")
        return value

    @model_validator(mode="after")
    def origin_matches_text(self) -> "QuickSource":
        if self.origin:
            if self.origin.text_sha256 != hashlib.sha256(self.text_fa.encode("utf-8")).hexdigest():
                raise ValueError("متن منبع با شناسه محتوای استخراج‌شده سازگار نیست")
            previous = 0
            for location in self.origin.locations:
                if location.start < previous or location.end > len(self.text_fa):
                    raise ValueError("محدوده مرجع استخراج نامعتبر است")
                previous = location.end
        return self


class QuickFact(Model):
    field: FinancialField
    value: Amount
    source_id: SourceId
    locator: str = Field(min_length=1, max_length=300)


class QuickFinancialInput(Model):
    period_start: date
    period_end: date
    amount_unit: Literal["IRR", "IRT"]
    facts: tuple[QuickFact, ...] = Field(default=(), max_length=17)
    requested_metrics: tuple[MetricKey, ...] = Field(default=get_args(MetricKey), min_length=1, max_length=12)

    def rial_values(self) -> dict[str, Decimal]:
        with localcontext(Context(prec=60)):
            factor = Decimal(10) if self.amount_unit == "IRT" else Decimal(1)
            return {
                fact.field: decimal_precision(fact.value * factor, digits=28, places=6) for fact in self.facts
            }

    @model_validator(mode="after")
    def consistent(self) -> QuickFinancialInput:
        if self.period_end <= self.period_start:
            raise ValueError("پایان دوره باید پس از شروع باشد")
        if len({fact.field for fact in self.facts}) != len(self.facts):
            raise ValueError("هر قلم مالی فقط یک مقدار می‌پذیرد")
        if len(set(self.requested_metrics)) != len(self.requested_metrics):
            raise ValueError("شاخص درخواستی تکراری است")
        v = self.rial_values()
        if any(amount < 0 for field, amount in v.items() if field in NONNEGATIVE):
            raise ValueError("مقدار این قلم مالی نباید منفی باشد")
        for part, total in (
            ("current_assets", "total_assets"),
            ("current_liabilities", "total_liabilities"),
            ("inventory", "current_assets"),
            ("prepayments", "current_assets"),
        ):
            if part in v and total in v and v[part] > v[total]:
                raise ValueError("جزء مالی نمی‌تواند بیشتر از کل متناظر باشد")
        with localcontext(Context(prec=60)):
            if {"total_assets", "total_liabilities", "equity"} <= v.keys():
                if v["total_assets"] != v["total_liabilities"] + v["equity"]:
                    raise ValueError("معادله دارایی = بدهی + حقوق مالکانه برقرار نیست")
            if {"current_assets", "inventory", "prepayments"} <= v.keys():
                if v["inventory"] + v["prepayments"] > v["current_assets"]:
                    raise ValueError("موجودی و پیش‌پرداخت بیشتر از دارایی جاری است")
        return self


def financial_context(value: QuickFinancialInput) -> dict:
    v = value.rial_values()
    facts = {fact.field: fact for fact in value.facts}
    ratios = {definition.key: definition for definition in RATIO_DEFINITIONS}
    results = []
    with localcontext(Context(prec=60)):
        for key in value.requested_metrics:
            if key in ratios:
                definition = ratios[key]
                fields, label, formula = definition.fields, definition.name_fa, definition.formula_fa
                unit = "fraction"
            else:
                closing = key == "closing_cash"
                fields = (
                    ("opening_cash", "cash_inflows", "cash_outflows")
                    if closing
                    else ("cash_inflows", "cash_outflows")
                )
                label = "نقد پایان دوره" if closing else "جریان نقد خالص"
                formula = "نقد ابتدا + ورودی نقد − خروجی نقد" if closing else "ورودی نقد − خروجی نقد"
                unit = "IRR"
            missing = [name for name in fields if name not in v]
            amount = None
            if not missing:
                if key in ratios:
                    amount = ratios[key].calculate(v)
                else:
                    amount = v["cash_inflows"] - v["cash_outflows"]
                    if key == "closing_cash":
                        amount += v["opening_cash"]
            status = "missing_inputs" if missing else "undefined" if amount is None else "available"
            results.append(
                dict(
                    key=key,
                    label_fa=label,
                    formula_fa=formula,
                    unit=unit,
                    value=str(amount) if amount is not None else None,
                    status=status,
                    missing_fields=missing,
                    reason_fa="اقلام لازم ارائه نشده‌اند؛ مقدار صفر فرض نشده است."
                    if missing
                    else "مخرج مثبت نیست؛ این نسبت قابل تفسیر نیست."
                    if amount is None
                    else None,
                    input_fields=list(fields),
                    inputs={
                        name: dict(
                            value_irr=str(v[name]),
                            source_id=facts[name].source_id,
                            locator=facts[name].locator,
                        )
                        for name in fields
                        if name in v
                    },
                )
            )
    return dict(
        metric_version="quick.financial.v1",
        input_verification="user_supplied_unverified",
        period_start=value.period_start.isoformat(),
        period_end=value.period_end.isoformat(),
        currency="IRR",
        supplied_unit=value.amount_unit,
        calculations=results,
        supplied_facts=[
            dict(**fact.model_dump(mode="json"), value_irr=str(v[fact.field])) for fact in value.facts
        ],
        limitations_fa=[
            "محاسبات فقط بر ارقام ارائه‌شده استوارند؛ صحت منبع و طبقه‌بندی اقلام تأیید نشده است.",
            "ارقام باید متعلق به یک بیزینس، یک دوره و واحد اعلام‌شده باشند؛ مقادیر آغاز دوره جداگانه مشخص شوند.",
            "نسبت‌ها به صورت کسر هستند؛ این محاسبات پیش‌بینی، تطبیق بانکی یا تأیید قانونی نیستند.",
        ],
    )
