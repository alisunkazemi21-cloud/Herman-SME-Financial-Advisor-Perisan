from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from src.models import Evidence, Model, Money


class CashFlow(Model):
    entry_date: date
    amount: Money
    category: Literal["operating", "investing", "financing"]
    evidence: Evidence


def summarize(flows: list[CashFlow]) -> dict[str, Decimal]:
    result = {key: Decimal(0) for key in ("operating", "investing", "financing")}
    for flow in flows:
        result[flow.category] += flow.amount
    result["net"] = sum(result.values(), Decimal(0))
    return result


def calculate_xirr(flows: list[CashFlow]) -> dict[str, object]:
    import pyxirr
    grouped: dict[date, Decimal] = {}
    for flow in flows:
        grouped[flow.entry_date] = grouped.get(flow.entry_date, Decimal(0)) + flow.amount
    points = [(day, amount) for day, amount in sorted(grouped.items()) if amount]
    signs = [amount > 0 for _, amount in points]
    if len(points) < 2 or all(signs) or not any(signs):
        raise ValueError("XIRR به پرداخت و دریافت در تاریخ‌های متفاوت نیاز دارد")
    if sum(a != b for a, b in zip(signs, signs[1:])) != 1:
        raise ValueError("جریان غیرمتعارف ممکن است چند ریشه داشته باشد؛ بررسی تخصصی لازم است")
    value = pyxirr.xirr([p[0] for p in points], [float(p[1]) for p in points], day_count="ACT/365F")
    return {"value": value, "day_count": "ACT/365F", "evidence": [f.evidence.model_dump() for f in flows],
            "note_fa": "بازده سالانه تقریبی؛ محاسبه عددی با اعشار شناور"}
