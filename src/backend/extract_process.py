"""Internal parser subprocess. No database credentials; only generated local paths are accepted by its parent."""
from __future__ import annotations

import json
import sys
import zipfile
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from src.ingestion.ocr_persian import PersianFinancialExtractor


def preflight(path: Path) -> None:
    if path.stat().st_size > 10 * 1024 * 1024:
        raise ValueError("input limit")
    if path.suffix == ".xlsx":
        with zipfile.ZipFile(path) as archive:
            if len(archive.infolist()) > 5000 or sum(i.file_size for i in archive.infolist()) > 100 * 1024 * 1024:
                raise ValueError("expanded archive limit")
    elif path.suffix == ".pdf":
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            if len(pdf.pages) > 100:
                raise ValueError("page limit")
    elif path.suffix not in (".csv", ".xlsx"):
        from PIL import Image
        with Image.open(path) as image:
            if image.width * image.height > 20_000_000:
                raise ValueError("image limit")


def main():
    source, destination, engine = sys.argv[1:]
    try:
        preflight(Path(source))
        extracted = PersianFinancialExtractor(engine).extract(source)
        packages = {}
        for package in ("pydantic", "openpyxl", "pdfplumber", "pillow", "pytesseract", "easyocr"):
            try:
                packages[package] = version(package)
            except PackageNotFoundError:
                pass
        result = dict(ok=True, document=extracted.model_dump(mode="json"), dependencies=packages)
        encoded = json.dumps(result, ensure_ascii=False)
        if len(encoded.encode()) > 20 * 1024 * 1024:
            result = dict(ok=False, code="resource_limit")
    except (ImportError, FileNotFoundError):
        result = dict(ok=False, code="engine_unavailable")
    except (ValueError, UnicodeError, zipfile.BadZipFile):
        result = dict(ok=False, code="invalid_document")
    except Exception:
        # Never persist parser exception text: it may contain confidential source content/paths.
        result = dict(ok=False, code="parser_failed")
    Path(destination).write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
