from datetime import date
from decimal import Decimal

import pytest

from src.ingestion.normalizer import normalize_persian_digits, parse_amount, parse_jalali
from src.ingestion.ocr_persian import DocumentType, PersianFinancialExtractor, document


def test_digits_letters_and_units():
    assert normalize_persian_digits("١۲۳ يك") == "123 یک"
    assert parse_amount("۱٬۲۰۰٫۵", "IRT") == Decimal("12005")
    assert parse_jalali("۱۴۰۵/۰۱/۰۱") == date(2026, 3, 21)


@pytest.mark.parametrize("bad", ["12,34", "NaN", "1e10", "۱۰۰ تومان", "", "--12"])
def test_bad_amount(bad):
    with pytest.raises(ValueError):
        parse_amount(bad)


def test_invalid_jalali():
    with pytest.raises(ValueError):
        parse_jalali("1400/12/30")


def test_low_confidence_retains_raw(evidence):
    result = document("فاکتور\nجمع کل ۱۰۰۰", evidence.source_file, "tesseract", 0.7)
    assert result.doc_type == DocumentType.INVOICE
    assert "۱۰۰۰" in result.raw_text_fa and "1000" in result.normalized_text
    assert result.requires_review and len(result.warnings_fa) == 2


def test_csv_persian_headers(tmp_path):
    file = tmp_path / "input.csv"
    file.write_text("تاریخ,مبلغ,شرح\n۱۴۰۵/۰۱/۰۱,۱۰۰۰,فاکتور\n", encoding="utf-8-sig")
    result = PersianFinancialExtractor().extract(str(file))
    row = result.structured_data["rows"][0]
    assert row["values"]["amount"] == "1000" and row["row"] == 2
    assert result.evidence.sha256


def test_xlsx_formula_rejected(tmp_path):
    import openpyxl
    book = openpyxl.Workbook()
    book.active.append(["مبلغ"])
    book.active.append(["=100+200"])
    path = tmp_path / "formula.xlsx"
    book.save(path)
    with pytest.raises(ValueError, match="فرمول"):
        PersianFinancialExtractor().extract(str(path))


def test_image_adapter_with_stub_not_accuracy_claim(tmp_path, monkeypatch):
    from PIL import Image
    path = tmp_path / "invoice.png"
    Image.new("RGB", (200, 100), "white").save(path)
    extractor = PersianFinancialExtractor()
    monkeypatch.setattr(extractor, "recognize", lambda image: ("فاکتور جمع کل ۱۰۰۰", 0.9))
    assert extractor.extract(str(path)).confidence == 0.9


def test_pdf_mixed_pages_adapter(tmp_path, monkeypatch):
    from src.ingestion.pdf_parser import extract_pdf
    path = tmp_path / "mixed.pdf"
    path.write_bytes(b"fixture for adapter only")
    class Page:
        def __init__(self, text):
            self.text = text
        def extract_text(self):
            return self.text
        def to_image(self, resolution):
            from types import SimpleNamespace
            return SimpleNamespace(original="image")
    class PDF:
        pages = [Page("فاکتور"), Page("")]
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
    monkeypatch.setattr("pdfplumber.open", lambda path: PDF())
    extractor = PersianFinancialExtractor()
    monkeypatch.setattr(extractor, "recognize", lambda image: ("جمع کل ۱۰۰۰", 0.7))
    result = extract_pdf(str(path), extractor)
    assert result.extraction_method == "pdf_mixed" and result.confidence == 0.7
    assert [r["page"] for r in result.structured_data["pages"]] == [1, 2]
