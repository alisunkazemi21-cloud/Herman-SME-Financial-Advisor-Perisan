from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID

from src.backend.database import AccessDenied
from src.backend.jobs import ExtractionQueue
from src.backend.service import Conflict
from src.ingestion.ocr_persian import ExtractedDocument


def process_one(queue: ExtractionQueue, token: str, business: UUID, timeout: int = 120) -> UUID | None:
    if not 1 <= timeout <= 120:
        raise ValueError("parser timeout must be between 1 and 120 seconds")
    actor = queue.database.authenticate(token)
    job = queue.claim(actor, business, lease_seconds=timeout + 60)
    if job is None:
        return None
    try:
        metadata, content = queue.service.read_document(actor, business, job["document_id"])
        with TemporaryDirectory(prefix="herman-extraction-") as folder:
            path = Path(folder) / ("source" + Path(metadata["original_name"]).suffix.lower())
            path.write_bytes(content)
            output = Path(folder) / "result.json"
            environment = {key: value for key, value in os.environ.items()
                           if key.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "LANG"}}
            subprocess.run([sys.executable, "-m", "src.backend.extract_process", str(path), str(output), job["engine"]],
                env=environment, cwd=folder, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, timeout=timeout, check=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if output.stat().st_size > 20 * 1024 * 1024:
                result = dict(ok=False, code="resource_limit")
            else:
                result = json.loads(output.read_text(encoding="utf-8"))
            # Re-authenticate before a write: revocation during extraction must take effect.
            actor = queue.database.authenticate(token)
            if result["ok"]:
                queue.complete(actor, business, job["id"], job["lease_token"],
                               ExtractedDocument.model_validate(result["document"]), result["dependencies"])
            else:
                queue.fail(actor, business, job["id"], job["lease_token"], result["code"], retryable=False)
    except Conflict:
        # A replaced/expired lease cannot be completed, failed, or otherwise overwritten.
        actor = queue.database.authenticate(token)
        try:
            queue.fail(actor, business, job["id"], job["lease_token"], "evidence_changed", retryable=False)
        except Conflict:
            pass
    except AccessDenied:
        raise
    except (ValueError, KeyError):
        actor = queue.database.authenticate(token)
        try:
            queue.fail(actor, business, job["id"], job["lease_token"], "parser_failed", retryable=False)
        except Conflict:
            pass
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, OSError) as exc:
        code = "timeout" if isinstance(exc, subprocess.TimeoutExpired) else (
            "parser_failed" if isinstance(exc, subprocess.CalledProcessError) else "storage_unavailable")
        actor = queue.database.authenticate(token)
        try:
            queue.fail(actor, business, job["id"], job["lease_token"], code, retryable=True)
        except Conflict:
            pass
    return job["id"]
