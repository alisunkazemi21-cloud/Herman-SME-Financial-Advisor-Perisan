from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.ingestion.ocr_persian import ExtractedDocument, document

if TYPE_CHECKING:
    from src.ingestion.ocr_persian import PersianFinancialExtractor


def extract_pdf(filepath: str, extractor: PersianFinancialExtractor) -> ExtractedDocument:
    import pdfplumber
    pages: list[dict[str, Any]] = []
    with pdfplumber.open(filepath) as pdf:
        for number, page in enumerate(pdf.pages, 1):
            text = page.extract_text() or ""
            score, method = 1.0, "pdf_text"
            if not text.strip():
                text, score = extractor.recognize(page.to_image(resolution=200).original)
                method = extractor.ocr_engine
            pages.append({"page": number, "text": text, "confidence": score, "method": method})
    return document("\n\n".join(p["text"] for p in pages), filepath, "pdf_mixed"
                    if any(p["method"] != "pdf_text" for p in pages) else "pdf_text",
                    min((p["confidence"] for p in pages), default=0.0), {"pages": pages})
