"""Durable tenant-scoped extraction queue; the calculator never consumes unreviewed output."""
from __future__ import annotations

from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from src.backend.service import Conflict, NotFound, Service, insert
from src.ingestion.ocr_persian import ExtractedDocument
from src.models import Model

SUFFIXES = {".csv", ".xlsx", ".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".bmp"}
ERROR_CODES = {"invalid_document", "engine_unavailable", "resource_limit", "timeout",
               "parser_failed", "storage_unavailable", "evidence_changed", "lease_exhausted"}


class ExtractionInput(Model):
    document_id: UUID
    engine: Literal["tesseract", "easyocr"] = "tesseract"


class ExtractionQueue:
    def __init__(self, service: Service):
        self.service = service
        self.database = service.database

    def enqueue(self, actor: UUID, business: UUID, key: str, value: ExtractionInput) -> UUID:
        def create(c):
            document = c.execute("SELECT original_name FROM herman.documents WHERE business_id=%s AND id=%s",
                                 (business, value.document_id)).fetchone()
            if document is None:
                raise NotFound("سند در این بیزینس موجود نیست")
            if Path(document["original_name"]).suffix.lower() not in SUFFIXES:
                raise ValueError("نوع فایل برای استخراج پشتیبانی نمی‌شود")
            identity = uuid4()
            insert(c, "extraction_jobs", dict(business_id=business, id=identity, document_id=value.document_id,
                                               engine=value.engine, created_by=actor))
            return identity

        return self.service._write(actor, business, key, "extraction.queued", value.model_dump(mode="json"), create)

    def read(self, actor: UUID, business: UUID, identity: UUID) -> dict:
        with self.database.transaction(actor, business) as c:
            row = c.execute("SELECT * FROM herman.extraction_jobs WHERE business_id=%s AND id=%s",
                            (business, identity)).fetchone()
            if row is None:
                raise NotFound("کار پردازش موجود نیست")
            row.pop("lease_token")
            row["extraction"] = c.execute("SELECT * FROM herman.extractions WHERE business_id=%s AND job_id=%s",
                                         (business, identity)).fetchone()
            return row

    def list(self, actor: UUID, business: UUID, after: UUID | None = None, limit: int = 50) -> list[dict]:
        if not 1 <= limit <= 100:
            raise ValueError("اندازه صفحه نامعتبر است")
        with self.database.transaction(actor, business) as c:
            return c.execute("SELECT id,document_id,engine,status,attempts,created_at,available_at,leased_until,error_code "
                "FROM herman.extraction_jobs WHERE business_id=%s AND (%s::uuid IS NULL OR id>%s) "
                "ORDER BY id LIMIT %s", (business, after, after, limit)).fetchall()

    def claim(self, actor: UUID, business: UUID, lease_seconds: int = 180) -> dict | None:
        if not 1 <= lease_seconds <= 600:
            raise ValueError("invalid lease duration")
        with self.database.transaction(actor, business, write=True, snapshot=False) as c:
            expired = c.execute("SELECT id FROM herman.extraction_jobs WHERE business_id=%s "
                "AND status='running' AND leased_until<=now() AND attempts=3 LIMIT 100 FOR UPDATE SKIP LOCKED",
                (business,)).fetchall()
            for row in expired:
                c.execute("UPDATE herman.extraction_jobs SET status='failed',lease_token=NULL,leased_until=NULL,"
                    "error_code='lease_exhausted' WHERE business_id=%s AND id=%s", (business, row["id"]))
                self.service._audit(c, actor, business, "extraction.lease_exhausted", row["id"])
            job = c.execute("SELECT * FROM herman.extraction_jobs WHERE business_id=%s AND attempts<3 AND "
                "((status='queued' AND available_at<=now()) OR (status='running' AND leased_until<=now())) "
                "ORDER BY available_at,created_at,id LIMIT 1 FOR UPDATE SKIP LOCKED", (business,)).fetchone()
            if job is None:
                return None
            row = c.execute("UPDATE herman.extraction_jobs SET status='running',attempts=attempts+1,"
                "lease_token=%s,leased_until=now()+%s*interval '1 second',error_code=NULL "
                "WHERE business_id=%s AND id=%s RETURNING *",
                (uuid4(), lease_seconds, business, job["id"])).fetchone()
            self.service._audit(c, actor, business, f"extraction.claimed.attempt_{row['attempts']}", row["id"])
            return row

    def _locked(self, c, business, identity, lease_token):
        row = c.execute("SELECT * FROM herman.extraction_jobs WHERE business_id=%s AND id=%s "
            "AND status='running' AND lease_token=%s AND leased_until>clock_timestamp() FOR UPDATE",
            (business, identity, lease_token)).fetchone()
        if row is None:
            raise Conflict("اجاره پردازش منقضی یا جایگزین شده است")
        return row

    def complete(self, actor: UUID, business: UUID, identity: UUID, lease_token: UUID,
                 extracted: ExtractedDocument, dependencies: dict[str, str]) -> UUID:
        with self.database.transaction(actor, business, write=True, snapshot=False) as c:
            job = self._locked(c, business, identity, lease_token)
            source = c.execute("SELECT sha256 FROM herman.documents WHERE business_id=%s AND id=%s",
                               (business, job["document_id"])).fetchone()
            if source["sha256"] != extracted.evidence.sha256:
                raise Conflict("هش خروجی استخراج با شاهد اصلی یکسان نیست")
            payload = extracted.model_dump(mode="json")
            payload.pop("source_file")
            payload.pop("evidence")
            payload.update(document_id=str(job["document_id"]), requires_review=True, dependencies=dependencies)
            result_id = uuid4()
            insert(c, "extractions", dict(business_id=business, id=result_id, job_id=identity,
                source_sha256=source["sha256"], parser_version="document.v1", payload=Jsonb(payload), created_by=actor))
            c.execute("UPDATE herman.extraction_jobs SET status='succeeded',lease_token=NULL,leased_until=NULL "
                      "WHERE business_id=%s AND id=%s", (business, identity))
            self.service._audit(c, actor, business, "extraction.succeeded", identity)
            return result_id

    def fail(self, actor: UUID, business: UUID, identity: UUID, lease_token: UUID,
             code: str, retryable: bool) -> None:
        if code not in ERROR_CODES:
            raise ValueError("unknown error code")
        with self.database.transaction(actor, business, write=True, snapshot=False) as c:
            job = self._locked(c, business, identity, lease_token)
            retry = retryable and job["attempts"] < 3
            c.execute("UPDATE herman.extraction_jobs SET status=%s,error_code=%s,lease_token=NULL,leased_until=NULL,"
                      "available_at=now()+%s*interval '1 second' WHERE business_id=%s AND id=%s",
                      ("queued" if retry else "failed", code, 30 * job["attempts"], business, identity))
            event = "extraction.retry_scheduled" if retry else "extraction.failed"
            self.service._audit(c, actor, business, f"{event}.{code}.attempt_{job['attempts']}", identity)
