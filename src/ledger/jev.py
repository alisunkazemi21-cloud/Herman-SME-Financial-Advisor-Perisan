from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import Field, model_validator

from src.ingestion.normalizer import parse_jalali
from src.models import Evidence, Model, Money

ACCOUNTS: dict[str, str] = {
    "1000": "نقد و بانک", "1100": "حساب‌های دریافتنی", "1200": "موجودی کالا",
    "1300": "پیش‌پرداخت", "1500": "دارایی ثابت", "1600": "سرقفلی",
    "2000": "حساب‌های پرداختنی", "2100": "اسناد پرداختنی", "2200": "ذخایر",
    "3000": "سرمایه", "3100": "سود انباشته", "4000": "درآمد عملیاتی",
    "5000": "بهای تمام‌شده", "5100": "هزینه عملیاتی", "5200": "هزینه بهره",
}


class JevEntry(Model):
    jev_id: str = Field(min_length=1, max_length=100)
    entry_date: date
    jalali_date: str
    description_fa: str = Field(min_length=3)
    debit_account: str
    credit_account: str
    amount: Money = Field(gt=0)
    evidence: Evidence
    evidence_ref: str = ""
    actor: str = Field(pattern=r"^(human|agent):\S+$")
    approved: Literal[False] = False
    currency: Literal["IRR"] = "IRR"
    extraction_confidence: float = Field(default=1.0, ge=0, le=1)
    reversal_of: str | None = None
    standards_review: list[Literal["16", "39", "43"]] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_entry(self) -> JevEntry:
        if self.debit_account not in ACCOUNTS or self.credit_account not in ACCOUNTS:
            raise ValueError("حساب در کدینگ تعریف نشده است")
        if self.debit_account == self.credit_account:
            raise ValueError("حساب بدهکار و بستانکار باید متفاوت باشند")
        if parse_jalali(self.jalali_date) != self.entry_date:
            raise ValueError("تاریخ شمسی و میلادی یکسان نیستند")
        if self.evidence_ref and self.evidence_ref != self.evidence.sha256:
            raise ValueError("شناسه شاهد با هش فایل یکسان نیست")
        object.__setattr__(self, "evidence_ref", self.evidence.sha256)
        return self


class Decision(Model):
    jev_id: str
    actor: str = Field(pattern=r"^human:\S+$")
    approved: bool
    reviewed_values: Literal[True]
    reason_fa: str = Field(min_length=3)


def explain_entry(entry: JevEntry, status_fa: str) -> str:
    amount = format(entry.amount, ",f").translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))
    return (f"سند {entry.jev_id}: مبلغ {amount} ریال در حساب «{ACCOUNTS[entry.debit_account]}» بدهکار "
            f"و به همان مبلغ در حساب «{ACCOUNTS[entry.credit_account]}» بستانکار پیشنهاد شده است. "
            f"شرح: {entry.description_fa}. وضعیت: {status_fa}. "
            "بدهکار/بستانکار جهت ثبت حسابداری است و به‌تنهایی به معنی ورود/خروج پول نیست.")
