from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from src.ingestion.normalizer import normalize_persian_digits
from src.ingestion.ocr_persian import ExtractedDocument, document

HEADERS = {"مبلغ": "amount", "مبلغ کل": "amount", "جمع کل": "amount", "تاریخ": "jalali_date",
           "شرح": "description_fa", "بدهکار": "debit", "بستانکار": "credit", "واحد": "unit"}


def extract_excel(filepath: str) -> ExtractedDocument:
    path = Path(filepath)
    sheets: dict[str, list[list[Any]]] = {}
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as handle:
            sheets["CSV"] = list(csv.reader(handle))
    else:
        import openpyxl
        book = openpyxl.load_workbook(path, read_only=True, data_only=False)
        try:
            for sheet in book:
                sheets[sheet.title] = [list(row) for row in sheet.iter_rows(values_only=True)]
        finally:
            book.close()
    records: list[dict[str, Any]] = []
    raw: list[str] = []
    for name, rows in sheets.items():
        if not rows:
            continue
        headers = [normalize_persian_digits(str(v or "")).strip() for v in rows[0]]
        mapped = [HEADERS.get(header, header) for header in headers]
        if any(not header for header in mapped) or len(set(mapped)) != len(mapped):
            raise ValueError("عنوان ستون خالی یا تکراری است")
        for number, row in enumerate(rows, 1):
            values = ["" if value is None else str(value) for value in row]
            if any(value.startswith("=") for value in values):
                raise ValueError("فرمول اکسل قابل اتکا نیست؛ خروجی مقادیر ثابت وارد کنید")
            raw.append(" | ".join(values))
            if number > 1:
                if len(values) != len(mapped):
                    raise ValueError("تعداد ستون‌های ردیف با عنوان‌ها یکسان نیست")
                records.append({"sheet": name, "row": number,
                                "values": dict(zip(mapped, map(normalize_persian_digits, values)))})
    return document("\n".join(raw), filepath, "excel" if path.suffix.lower() == ".xlsx" else "csv",
                    1.0 if records else 0.0, {"rows": records})
