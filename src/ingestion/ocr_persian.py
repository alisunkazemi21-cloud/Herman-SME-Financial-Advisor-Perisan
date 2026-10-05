from __future__ import annotations

import re
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from src.ingestion.invoice_fields import extract_invoice_amounts
from src.ingestion.normalizer import normalize_persian_digits, parse_jalali
from src.models import Evidence, Model


class DocumentType(str, Enum):
    INVOICE = "فاکتور"
    BALANCE_SHEET = "ترازنامه"
    INCOME_STATEMENT = "صورت سود و زیان"
    CASH_FLOW = "صورت جریان وجوه نقد"
    BANK_STATEMENT = "صورت حساب بانکی"
    PAYROLL = "لیست حقوق"
    TAX_FORM = "اظهارنامه مالیاتی"
    UNKNOWN = "نامشخص"


class ExtractedDocument(Model):
    doc_type: DocumentType = DocumentType.UNKNOWN
    raw_text_fa: str
    normalized_text: str
    structured_data: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(ge=0, le=1)
    source_file: str
    evidence: Evidence
    extraction_method: str
    jalali_date: str | None = None
    persian_digits_normalized: bool = True
    warnings_fa: list[str] = Field(default_factory=list)

    @property
    def requires_review(self) -> bool:
        return True


def document(text: str, path: str | Path, method: str, confidence: float,
             structured: dict[str, Any] | None = None) -> ExtractedDocument:
    normalized = normalize_persian_digits(text)
    kind = next((item for item in DocumentType if item.value in normalized), DocumentType.UNKNOWN)
    warnings = ["استخراج به تأیید انسانی نیاز دارد"]
    if confidence < 0.8:
        warnings.append("اطمینان استخراج کمتر از ۰٫۸ است؛ بازبینی مقدارها الزامی است")
    dates = re.findall(r"\b1[34]\d{2}/\d{1,2}/\d{1,2}\b", normalized)
    jalali = None
    if dates:
        try:
            parse_jalali(dates[0])
            jalali = dates[0]
        except ValueError:
            warnings.append("تاریخ استخراج‌شده نامعتبر است")
    fields = dict(structured or {})
    fields["invoice_amount_candidates"] = [candidate.model_dump(mode="json")
                                            for candidate in extract_invoice_amounts(text)]
    return ExtractedDocument(doc_type=kind, raw_text_fa=text, normalized_text=normalized,
                             structured_data=fields, confidence=confidence,
                             source_file=str(Path(path).resolve()), evidence=Evidence.from_file(path),
                             extraction_method=method, jalali_date=jalali, warnings_fa=warnings)


class PersianFinancialExtractor:
    def __init__(self, ocr_engine: Literal["tesseract", "easyocr"] = "tesseract",
                 model_directory: str | None = None) -> None:
        if ocr_engine not in ("tesseract", "easyocr"):
            raise ValueError("موتور OCR پشتیبانی نمی‌شود")
        self.ocr_engine = ocr_engine
        self.model_directory = model_directory
        self.reader: Any = None

    normalize_persian_digits = staticmethod(normalize_persian_digits)

    def recognize(self, image: Any) -> tuple[str, float]:
        if self.ocr_engine == "easyocr":
            import easyocr
            import numpy as np
            if self.reader is None:
                self.reader = easyocr.Reader(["fa", "en"], gpu=False, download_enabled=False,
                                             model_storage_directory=self.model_directory)
            rows = self.reader.readtext(np.array(image), detail=1)
            texts = [str(row[1]) for row in rows]
            scores = [float(row[2]) for row in rows]
        else:
            import pytesseract
            data = pytesseract.image_to_data(image, lang="fas+eng", output_type=pytesseract.Output.DICT)
            indices = [i for i, text in enumerate(data["text"]) if text.strip()]
            texts = [data["text"][i] for i in indices]
            scores = [max(0.0, float(data["conf"][i])) / 100 for i in indices]
        return "\n".join(texts), min(scores, default=0.0)

    def extract_from_image(self, filepath: str) -> ExtractedDocument:
        from PIL import Image
        with Image.open(filepath) as image:
            text, score = self.recognize(image.convert("RGB"))
        return document(text, filepath, self.ocr_engine, score)

    def extract_from_excel(self, filepath: str) -> ExtractedDocument:
        from src.ingestion.excel_parser import extract_excel
        return extract_excel(filepath)

    def extract_from_pdf(self, filepath: str) -> ExtractedDocument:
        from src.ingestion.pdf_parser import extract_pdf
        return extract_pdf(filepath, self)

    def extract(self, filepath: str) -> ExtractedDocument:
        suffix = Path(filepath).suffix.lower()
        if suffix in (".xlsx", ".csv"):
            return self.extract_from_excel(filepath)
        if suffix == ".pdf":
            return self.extract_from_pdf(filepath)
        if suffix in (".png", ".jpg", ".jpeg", ".tiff", ".bmp"):
            return self.extract_from_image(filepath)
        raise ValueError("نوع فایل پشتیبانی نمی‌شود")
