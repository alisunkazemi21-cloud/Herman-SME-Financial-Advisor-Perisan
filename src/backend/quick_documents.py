"""Temporary local extraction; deliberately has no service or database dependency."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from src.backend.process_guard import run_contained
from src.backend.quick_document_models import (
    MAX_CHILD_OUTPUT,
    MAX_SOURCES_BYTES,
    MAX_TEXT,
    MAX_UPLOAD,
    PARSER_SECONDS,
    DocumentError,
    DocumentFormat,
    ExtractedUnit,
    OcrEngine,
    QuickOrigin,
    SourceLocation,
)
from src.backend.quick_financial import QuickSource


def pack_sources(units: list[ExtractedUnit], digest: str, format: DocumentFormat) -> list[dict]:
    if not units or len(units) > 2000 or sum(len(unit.text.encode("utf-8")) for unit in units) > MAX_TEXT:
        raise DocumentError("resource_limit")
    sources: list[dict] = []
    text = ""
    locations: list[SourceLocation] = []

    def flush() -> None:
        nonlocal text, locations
        if not locations:
            return
        if len(sources) == 8:
            raise DocumentError("resource_limit")
        source = QuickSource(
            source_id=f"q_{digest[:56]}_{len(sources) + 1}", title_fa=f"سند موقت · بخش {len(sources) + 1}",
            text_fa=text, origin=QuickOrigin(file_sha256=digest, format=format,
                                           text_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                                           locations=tuple(locations)),
        )
        sources.append(source.model_dump(mode="json"))
        text, locations = "", []

    for unit in units:
        if text and len(text) < 6000:
            text += "\n"
        offset = 0
        while offset < len(unit.text):
            if len(text) == 6000:
                flush()
            part = unit.text[offset:offset + 6000 - len(text)]
            locations.append(SourceLocation(locator=unit.locator, start=len(text), end=len(text) + len(part),
                                            unit_offset=offset, method=unit.method, confidence=unit.confidence))
            text += part
            offset += len(part)
    flush()
    if len(json.dumps(sources, ensure_ascii=False).encode("utf-8")) > MAX_SOURCES_BYTES:
        raise DocumentError("resource_limit")
    return sources


def extract_temporary(content: bytes, format: DocumentFormat, engine: OcrEngine = "tesseract",
                      *, timeout: float = PARSER_SECONDS, temporary_parent: Path | None = None) -> dict:
    if not content or len(content) > MAX_UPLOAD:
        raise DocumentError("resource_limit")
    # Validate internal callers too; neither value may become a path or arbitrary command argument.
    if format not in ("csv", "xlsx", "pdf", "png", "jpg", "jpeg", "tiff", "bmp"):
        raise DocumentError("invalid_document")
    if engine not in ("tesseract", "easyocr"):
        raise DocumentError("invalid_document")
    digest = hashlib.sha256(content).hexdigest()
    try:
        with TemporaryDirectory(prefix="herman-quick-", dir=temporary_parent) as directory:
            folder = Path(directory)
            source, output = folder / f"source.{format}", folder / "result.json"
            source.write_bytes(content)
            model_directory = str(Path.home() / ".EasyOCR" / "model") if engine == "easyocr" else "-"
            run_contained([sys.executable, "-m", "src.backend.quick_extract_process",
                           str(source), str(output), engine, model_directory], folder, timeout)
            if not output.is_file() or output.stat().st_size > MAX_CHILD_OUTPUT:
                raise DocumentError("resource_limit")
            payload = json.loads(output.read_text(encoding="utf-8"))
            if payload.get("ok") is not True:
                raise DocumentError(payload.get("code", "parser_failed"))
            units = [ExtractedUnit.model_validate(unit) for unit in payload["units"]]
            sources = pack_sources(units, digest, format)
            dependencies = payload["dependencies"]
            if not isinstance(dependencies, dict) or any(not isinstance(v, str) for v in dependencies.values()):
                raise DocumentError("parser_failed")
        return dict(
            profile="quick.document.v1", document=dict(sha256=digest, format=format, bytes=len(content)),
            sources=sources, dependencies=dependencies, verification="locally_extracted_unverified",
            persisted=False, history_used=False,
            limitations_fa=[
                "متن و ارجاع‌های استخراج‌شده تأیید مالی نیستند؛ مقدارها و واحدها را بازبینی کنید.",
                "برای محاسبه، ارقام مالی را صریح وارد کنید؛ متن سند به‌طور خودکار به رقم مالی تبدیل نمی‌شود.",
                "مرجع‌های بازفرستاده‌شده در درخواست بعدی ادعای کاربرند؛ فایل اصلی نگهداری نمی‌شود.",
            ],
        )
    except DocumentError:
        raise
    except subprocess.TimeoutExpired:
        raise DocumentError("timeout") from None
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError):
        raise DocumentError("parser_failed") from None
