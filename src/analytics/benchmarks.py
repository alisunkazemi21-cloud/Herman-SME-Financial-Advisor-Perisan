from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import field_validator

from src.models import Fact, Model


class Quote(Model):
    day: date
    asset: Literal["USD", "GOLD_18K_GRAM"]
    irr_per_unit: Fact


class BenchmarkRequest(Model):
    amount_irr: Fact
    start: Quote
    end: Quote

    @field_validator("amount_irr")
    @classmethod
    def nonnegative(cls, value: Fact) -> Fact:
        if value.value < 0:
            raise ValueError("مبلغ مقایسه نباید منفی باشد")
        return value


def compare(request: BenchmarkRequest) -> dict[str, object]:
    start, end = request.start, request.end
    if start.asset != end.asset or start.day >= end.day:
        raise ValueError("دارایی و ترتیب تاریخ نرخ‌ها باید یکسان و معتبر باشند")
    if start.irr_per_unit.value <= 0 or end.irr_per_unit.value <= 0:
        raise ValueError("نرخ باید مثبت باشد")
    units = request.amount_irr.value / start.irr_per_unit.value
    return {"units": str(units), "ending_value_irr": str(units * end.irr_per_unit.value),
            "nominal_return": str(end.irr_per_unit.value / start.irr_per_unit.value - 1),
            "evidence": [request.amount_irr.model_dump(mode="json"),
                         start.model_dump(mode="json"), end.model_dump(mode="json")],
            "note_fa": "مقایسه فرضی بدون کارمزد، مالیات یا تعدیل تورم؛ توصیه خرید نیست"}
