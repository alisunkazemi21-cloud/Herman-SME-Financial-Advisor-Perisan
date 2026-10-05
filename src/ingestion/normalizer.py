from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Literal

import jdatetime


def normalize_persian_digits(text: str) -> str:
    return text.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩يك٫٬−", "01234567890123456789یک.,-"))


def parse_amount(text: str, unit: Literal["IRR", "IRT"] = "IRR") -> Decimal:
    value = normalize_persian_digits(text).strip()
    if not re.fullmatch(r"[+-]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?", value):
        raise ValueError("قالب مبلغ نامعتبر یا مبهم است")
    if unit not in ("IRR", "IRT"):
        raise ValueError("واحد باید ریال یا تومان باشد")
    try:
        return Decimal(value.replace(",", "")) * (10 if unit == "IRT" else 1)
    except InvalidOperation as exc:
        raise ValueError("مبلغ نامعتبر") from exc


def parse_jalali(text: str) -> date:
    value = normalize_persian_digits(text).replace("-", "/")
    if not re.fullmatch(r"\d{4}/\d{1,2}/\d{1,2}", value):
        raise ValueError("تاریخ شمسی باید سال/ماه/روز باشد")
    year, month, day = map(int, value.split("/"))
    return jdatetime.date(year, month, day).togregorian()


def to_jalali(value: date) -> str:
    return jdatetime.date.fromgregorian(date=value).strftime("%Y/%m/%d")
