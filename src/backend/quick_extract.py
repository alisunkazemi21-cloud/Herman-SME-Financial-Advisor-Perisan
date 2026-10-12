"""Local bounded document reading; no financial mapping, storage or inference."""

from __future__ import annotations

import csv
import json
import math
import os
import shutil
import sys
import zipfile
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from src.backend.quick_document_models import (
    MAX_CELLS,
    MAX_CHILD_OUTPUT,
    MAX_COLUMNS,
    MAX_ROWS,
    MAX_TEXT,
    MAX_UPLOAD,
    DocumentError,
    ExtractedUnit,
    OcrEngine,
)
from src.ingestion.ocr_persian import PersianFinancialExtractor


def extract_units(path: Path, engine: OcrEngine, model_directory: str | None = None) -> list[ExtractedUnit]:
    if not 0 < path.stat().st_size <= MAX_UPLOAD:
        raise DocumentError("resource_limit")
    units: list[ExtractedUnit] = []
    text_bytes = cells = rows = 0
    meaningful = False

    def add(locator: str, text: str, method: str, confidence: float = 1.0) -> None:
        nonlocal text_bytes
        text_bytes += len(text.encode("utf-8"))
        if text_bytes > MAX_TEXT:
            raise DocumentError("resource_limit")
        if not text.strip():
            raise DocumentError("no_text")
        units.append(ExtractedUnit(locator=locator, text=text, method=method, confidence=confidence))

    def row(name: str, number: int, values: list[Any], method: str) -> None:
        nonlocal rows, cells, meaningful
        rows += 1
        cells += len(values)
        if rows > MAX_ROWS or len(values) > MAX_COLUMNS or cells > MAX_CELLS:
            raise DocumentError("resource_limit")
        strings = ["" if value is None else str(value) for value in values]
        if any(len(value) > 6000 for value in strings):
            raise DocumentError("resource_limit")
        if any(value.lstrip().startswith("=") for value in strings):
            raise DocumentError("unsupported_document")
        meaningful |= any(value.strip() for value in strings)
        add(f"{name}:row:{number}", json.dumps(strings, ensure_ascii=False), method)

    def recognize(image: Any) -> tuple[str, float]:
        if engine == "tesseract" and shutil.which("tesseract") is None:
            raise DocumentError("engine_unavailable")
        if engine == "easyocr" and (model_directory is None or not Path(model_directory).is_dir()):
            raise DocumentError("engine_unavailable")
        try:
            if engine == "tesseract":
                import pytesseract
                if not {"fas", "eng"}.issubset(pytesseract.get_languages()):
                    raise DocumentError("engine_unavailable")
            return extractor.recognize(image)
        except (ImportError, FileNotFoundError):
            raise DocumentError("engine_unavailable") from None

    # EasyOCR may create auxiliary directories even with downloads disabled.
    # Keep those in the request directory; preinstalled model weights are read separately.
    os.environ["EASYOCR_MODULE_PATH"] = str(path.parent / "ocr-scratch")
    extractor = PersianFinancialExtractor(engine, model_directory=model_directory)
    suffix = path.suffix
    if suffix == ".csv":
        csv.field_size_limit(MAX_UPLOAD)
        with path.open(encoding="utf-8-sig", newline="") as stream:
            for number, values in enumerate(csv.reader(stream, strict=True), 1):
                row("CSV", number, values, "csv")
    elif suffix == ".xlsx":
        import openpyxl

        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if len(entries) > 5000 or sum(entry.file_size for entry in entries) > 25 * 1024 * 1024:
                raise DocumentError("resource_limit")
        book = openpyxl.load_workbook(path, read_only=True, data_only=False, keep_links=False)
        try:
            if len(book.worksheets) > 16:
                raise DocumentError("resource_limit")
            for sheet in book:
                # Do not trust undersized worksheet dimension metadata to omit actual rows.
                sheet.reset_dimensions()
                for number, values in enumerate(sheet.iter_rows(), 1):
                    if any(cell.data_type == "f" for cell in values):
                        raise DocumentError("unsupported_document")
                    row(sheet.title, number, [cell.value for cell in values], "xlsx")
        finally:
            book.close()
    elif suffix == ".pdf":
        import pdfplumber

        with pdfplumber.open(path) as pdf:
            if len(pdf.pages) > 8:
                raise DocumentError("resource_limit")
            pixels = 0
            for number, page in enumerate(pdf.pages, 1):
                area = math.ceil(float(page.width) * 200 / 72) * math.ceil(float(page.height) * 200 / 72)
                pixels += area
                if area > 20_000_000 or pixels > 40_000_000:
                    raise DocumentError("resource_limit")
                text, method, confidence = page.extract_text() or "", "pdf_text", 1.0
                if not text.strip():
                    image = page.to_image(resolution=200).original
                    try:
                        text, confidence = recognize(image)
                    finally:
                        image.close()
                    method = engine
                add(f"page:{number}", text, method, confidence)
        meaningful = bool(units)
    else:
        from PIL import Image

        with Image.open(path) as image:
            expected = {".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG", ".tiff": "TIFF", ".bmp": "BMP"}
            if expected.get(suffix) != image.format:
                raise DocumentError("invalid_document")
            if image.width * image.height > 20_000_000:
                raise DocumentError("resource_limit")
            if getattr(image, "n_frames", 1) != 1:
                raise DocumentError("unsupported_document")
            with image.convert("RGB") as rgb:
                text, confidence = recognize(rgb)
            add("image:1", text, engine, confidence)
        meaningful = True
    if not units or not meaningful:
        raise DocumentError("no_text")
    return units


def main() -> None:
    source, destination, engine, model_directory = sys.argv[1:]
    try:
        units = extract_units(Path(source), engine, None if model_directory == "-" else model_directory)
        dependencies = {}
        for package in ("pydantic", "openpyxl", "pdfplumber", "pillow", "pytesseract", "easyocr"):
            try:
                dependencies[package] = version(package)
            except PackageNotFoundError:
                pass
        result = dict(ok=True, units=[unit.model_dump(mode="json") for unit in units], dependencies=dependencies)
        if len(json.dumps(result, ensure_ascii=False).encode("utf-8")) > MAX_CHILD_OUTPUT:
            raise DocumentError("resource_limit")
    except DocumentError as exc:
        result = dict(ok=False, code=exc.code)
    except (ValueError, UnicodeError, csv.Error, zipfile.BadZipFile, OSError):
        result = dict(ok=False, code="invalid_document")
    except ImportError:
        result = dict(ok=False, code="engine_unavailable")
    except Exception:
        # Never return parser exception text, paths or source snippets.
        result = dict(ok=False, code="parser_failed")
    Path(destination).write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
