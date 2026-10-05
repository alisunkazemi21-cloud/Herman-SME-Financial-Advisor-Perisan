from __future__ import annotations

import re
from typing import Literal

from pydantic import Field

from src.ingestion.normalizer import normalize_persian_digits, parse_amount
from src.models import Model, Money


class InvoiceAmountCandidate(Model):
    label_fa: str
    raw_fragment: str
    normalized_amount: str
    unit: Literal["IRR", "IRT"] | None
    amount_irr: Money | None
    normalized_start: int = Field(ge=0)
    normalized_end: int = Field(gt=0)
    needs_review: Literal[True] = True
    warning_fa: str


def extract_invoice_amounts(text: str) -> list[InvoiceAmountCandidate]:
    """Conservative labelled candidates, not an invoice-total selection or posting decision."""
    normalized = normalize_persian_digits(text)
    pattern = re.compile(r"(?P<label>جمع\s+کل|مبلغ\s+کل|مبلغ\s+قابل\s+پرداخت)\s*[:：]?\s*"
                         r"(?P<number>[+-]?\d[\d,.]*)\s*(?P<unit>ریال|تومان)?")
    candidates: list[InvoiceAmountCandidate] = []
    for match in pattern.finditer(normalized):
        unit = {"ریال": "IRR", "تومان": "IRT"}.get(match.group("unit"))
        amount = None
        warning = "واحد مبلغ مشخص نیست؛ انتخاب واحد توسط انسان الزامی است"
        if unit:
            try:
                amount = parse_amount(match.group("number"), unit)
                warning = "مبلغ نامزد استخراج است؛ با تصویر و جمع اقلام تطبیق دهید"
            except ValueError:
                warning = "قالب مبلغ مبهم است؛ مقدار باید از شاهد بازخوانی شود"
        candidates.append(InvoiceAmountCandidate(label_fa=match.group("label"),
            raw_fragment=text[match.start():match.end()], normalized_amount=match.group("number"),
            unit=unit, amount_irr=amount, normalized_start=match.start(), normalized_end=match.end(),
            warning_fa=warning))
    return candidates
