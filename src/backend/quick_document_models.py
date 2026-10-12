"""Bounded, unverified extraction references carried by request-only Quick sources."""

from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from src.models import Model

DocumentFormat = Literal["csv", "xlsx", "pdf", "png", "jpg", "jpeg", "tiff", "bmp"]
OcrEngine = Literal["tesseract", "easyocr"]
Method = Literal["csv", "xlsx", "pdf_text", "tesseract", "easyocr"]
Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
RawText = Annotated[str, StringConstraints(strip_whitespace=False)]

MAX_UPLOAD = 10 * 1024 * 1024
MAX_TEXT = 40 * 1024
MAX_SOURCES_BYTES = 48 * 1024
MAX_CHILD_OUTPUT = 512 * 1024
MAX_ROWS, MAX_COLUMNS, MAX_CELLS = 2000, 50, 20000
PARSER_SECONDS, RECEIVE_SECONDS = 60, 30


class SourceLocation(Model):
    locator: RawText = Field(min_length=1, max_length=160)
    start: int = Field(ge=0, lt=6000, strict=True)
    end: int = Field(gt=0, le=6000, strict=True)
    unit_offset: int = Field(ge=0, le=MAX_TEXT, strict=True)
    method: Method
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def ordered(self) -> "SourceLocation":
        if self.end <= self.start:
            raise ValueError("محدوده مرجع استخراج نامعتبر است")
        return self


class QuickOrigin(Model):
    profile: Literal["quick.document.v1"] = "quick.document.v1"
    file_sha256: Digest
    text_sha256: Digest
    format: DocumentFormat
    locations: tuple[SourceLocation, ...] = Field(min_length=1, max_length=MAX_ROWS)


class ExtractedUnit(Model):
    locator: RawText = Field(min_length=1, max_length=160)
    text: RawText = Field(min_length=1, max_length=MAX_TEXT)
    method: Method
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)


ERRORS = {
    "resource_limit": (413, "سند از محدودیت پردازش بیشتر است؛ بخش کوچک‌تری ارسال کنید"),
    "invalid_document": (422, "سند قابل خواندن نیست یا قالب آن با نوع انتخاب‌شده سازگار نیست"),
    "unsupported_document": (422, "فرمول یا تصویر چندفریمی پشتیبانی نمی‌شود؛ مقادیر ثابت یا تک‌فریم بفرستید"),
    "no_text": (422, "متن قابل استفاده‌ای استخراج نشد؛ کیفیت یا محتوای سند را بررسی کنید"),
    "engine_unavailable": (503, "موتور OCR یا مدل تشخیص متن روی این دستگاه موجود نیست"),
    "parser_failed": (503, "استخراج سند انجام نشد؛ دوباره تلاش کنید"),
    "timeout": (504, "زمان پردازش سند تمام شد؛ بخش کوچک‌تری ارسال کنید"),
    "receive_timeout": (408, "زمان دریافت سند تمام شد"),
    "busy": (503, "پردازش سند دیگری در جریان است؛ کمی بعد تلاش کنید"),
}


class DocumentError(Exception):
    def __init__(self, code: str):
        self.code = code if code in ERRORS else "parser_failed"
        self.status, self.detail = ERRORS[self.code]
        super().__init__(self.code)
