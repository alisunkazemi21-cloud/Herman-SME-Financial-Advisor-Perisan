"""Explicit extracted table mapping to balanced, unapproved journal entries."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date
from decimal import Decimal, localcontext
from typing import Annotated, Literal
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.types.json import Jsonb
from pydantic import Field, model_validator

from src.backend.imports import Column
from src.backend.journal_sources import journal_origins
from src.backend.journals import JournalInput, Journals
from src.backend.service import Conflict, NotFound, Service, insert
from src.ingestion.normalizer import normalize_persian_digits, parse_amount, parse_jalali, to_jalali
from src.models import Model


class JournalImport(Model):
    extraction_id: UUID
    sheet: str = Field(min_length=1, max_length=200)
    rows: tuple[Annotated[int, Field(ge=2, le=1048576, strict=True)], ...] = Field(
        min_length=2, max_length=500
    )
    voucher_column: Column
    account_column: Column
    debit_column: Column
    credit_column: Column
    date_column: Column
    description_column: Column
    date_kind: Literal["jalali", "gregorian"]
    amount_unit: Literal["IRR", "IRT"]

    @model_validator(mode="after")
    def unique(self) -> JournalImport:
        if len(set(self.rows)) != len(self.rows):
            raise ValueError("ردیف منبع تکراری است")
        columns = (
            self.voucher_column,
            self.account_column,
            self.debit_column,
            self.credit_column,
            self.date_column,
            self.description_column,
        )
        if len(set(columns)) != len(columns):
            raise ValueError("هر نقش باید به ستون جداگانه نگاشت شود")
        return self


def cell(row: dict, name: str, blank: bool = False) -> str:
    value = row.get("values", {}).get(name)
    if not isinstance(value, str) or (not blank and not value.strip()):
        raise ValueError("ستون انتخاب‌شده موجود نیست یا مقدار لازم خالی است")
    return value.strip()


def amount_cell(row: dict, name: str, unit: Literal["IRR", "IRT"]) -> Decimal:
    text = cell(row, name, blank=True)
    if not text:
        return Decimal(0)
    if len(text) > 64:
        raise ValueError("طول مبلغ منبع بیش از حد است")
    # Preserve excessive fractional digits until the journal validator rejects them.
    with localcontext() as ctx:
        ctx.prec = 80
        value = parse_amount(text, unit)
    if value < 0:
        raise ValueError("مبلغ بدهکار و بستانکار نباید منفی باشد")
    return value


def proposals(
    payload: dict, value: JournalImport, document: UUID
) -> list[tuple[str, JournalInput, list[dict]]]:
    sheet = [r for r in payload.get("structured_data", {}).get("rows", []) if r.get("sheet") == value.sheet]
    indexed = {r["row"]: r for r in sheet}
    if len(indexed) != len(sheet) or not set(value.rows) <= set(indexed):
        raise ValueError("ردیف‌های انتخاب‌شده موجود یا یکتا نیستند")
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in sheet:
        if not any(str(v).strip() for v in row.get("values", {}).values()):
            continue
        key = cell(row, value.voucher_column)
        if len(key) > 100:
            raise ValueError("شناسه سند منبع بیش از حد طولانی است")
        grouped[key].append(row)
    keys = {cell(indexed[number], value.voucher_column) for number in value.rows}
    complete = {row["row"] for key in keys for row in grouped[key]}
    if complete != set(value.rows):
        raise ValueError("تمام ردیف‌های هر سند انتخاب‌شده باید با هم وارد شوند")
    result = []
    for key in sorted(keys):
        rows = sorted(grouped[key], key=lambda row: row["row"])
        dates, descriptions, lines = set(), set(), []
        for row in rows:
            raw_date = cell(row, value.date_column)
            normalized_date = normalize_persian_digits(raw_date)
            if value.date_kind == "gregorian" and not re.fullmatch(
                r"[0-9]{4}-[0-9]{2}-[0-9]{2}", normalized_date
            ):
                raise ValueError("تاریخ میلادی باید با قالب YYYY-MM-DD وارد شود")
            occurred = (
                parse_jalali(raw_date) if value.date_kind == "jalali" else date.fromisoformat(normalized_date)
            )
            dates.add(occurred)
            descriptions.add(cell(row, value.description_column))
            debit, credit = (
                amount_cell(row, value.debit_column, value.amount_unit),
                amount_cell(row, value.credit_column, value.amount_unit),
            )
            if (debit > 0) == (credit > 0):
                raise ValueError("در هر ردیف دقیقاً یکی از بدهکار یا بستانکار باید مثبت باشد")
            lines.append(
                dict(
                    account_code=cell(row, value.account_column),
                    side="debit" if debit else "credit",
                    amount=debit or credit,
                    evidence=dict(document_id=document, locator=f"{value.sheet}:row:{row['row']}"),
                )
            )
        if len(dates) != 1 or len(descriptions) != 1:
            raise ValueError("تاریخ و شرح ردیف‌های یک سند باید یکسان باشند")
        occurred = next(iter(dates))
        result.append(
            (
                key,
                JournalInput(
                    entry_date=occurred,
                    jalali_date=to_jalali(occurred),
                    description_fa=next(iter(descriptions)),
                    lines=lines,
                ),
                rows,
            )
        )
    return result


class JournalImporter:
    def __init__(self, service: Service) -> None:
        self.service = service
        self.journals = Journals(service)

    def _prepare(
        self, c: Connection, business: UUID, value: JournalImport
    ) -> tuple[dict, list[tuple[str, JournalInput, list[dict]]]]:
        extraction = c.execute(
            "SELECT e.*,j.document_id FROM herman.extractions e JOIN herman.extraction_jobs j "
            "ON (j.business_id,j.id)=(e.business_id,e.job_id) WHERE e.business_id=%s AND e.id=%s AND j.status='succeeded'",
            (business, value.extraction_id),
        ).fetchone()
        if extraction is None:
            raise NotFound("استخراج موفق در این بیزینس موجود نیست")
        if extraction["payload"].get("extraction_method") not in ("csv", "excel"):
            raise ValueError("ورود سند حسابداری فقط از جدول CSV/XLSX پشتیبانی می‌شود")
        hashes = self.journals._verify(c, business, {extraction["document_id"]})
        if hashes[str(extraction["document_id"])] != extraction["source_sha256"]:
            raise Conflict("هش استخراج و سند منبع یکسان نیست")
        if c.execute(
            "SELECT 1 FROM herman.journal_import_sources WHERE business_id=%s AND source_sha256=%s AND sheet=%s AND source_row=ANY(%s)",
            (business, extraction["source_sha256"], value.sheet, list(value.rows)),
        ).fetchone():
            raise Conflict("ردیف انتخاب‌شده از همین محتوای فایل قبلاً وارد شده است")
        mapped = proposals(extraction["payload"], value, extraction["document_id"])
        accounts = {line.account_code for _, proposal, _ in mapped for line in proposal.lines}
        existing = {
            r["code"]
            for r in c.execute(
                "SELECT code FROM herman.journal_accounts WHERE business_id=%s AND code=ANY(%s)",
                (business, list(accounts)),
            ).fetchall()
        }
        if existing != accounts:
            raise ValueError("حساب منبع در کاتالوگ این بیزینس تعریف نشده است")
        return extraction, mapped

    def preview(self, actor: UUID, business: UUID, value: JournalImport) -> dict:
        with self.service.database.transaction(actor, business) as c:
            extraction, mapped = self._prepare(c, business, value)
            return dict(
                persisted=False,
                source_sha256=extraction["source_sha256"],
                parser_version=extraction["parser_version"],
                entries=[
                    dict(
                        voucher_key=key,
                        source_rows=[row["row"] for row in rows],
                        proposal=proposal.model_dump(mode="json"),
                    )
                    for key, proposal, rows in mapped
                ],
                explanation_fa="این پیش‌نمایش ذخیره نشده است؛ ورود نهایی فقط پیشنهاد می‌سازد و برای ثبت مالی تأیید انسان لازم است.",
            )

    def create(self, actor: UUID, business: UUID, key: str, value: JournalImport) -> UUID:
        def store(c: Connection) -> UUID:
            extraction, mapped = self._prepare(c, business, value)
            identity = uuid4()
            insert(
                c,
                "journal_import_batches",
                dict(
                    business_id=business,
                    id=identity,
                    extraction_id=value.extraction_id,
                    document_id=extraction["document_id"],
                    source_sha256=extraction["source_sha256"],
                    mapping=Jsonb(value.model_dump(mode="json")),
                    created_by=actor,
                ),
            )
            for _, proposal, rows in mapped:
                entry = self.journals._store(c, actor, business, proposal)
                for number, row in enumerate(rows, 1):
                    insert(
                        c,
                        "journal_import_sources",
                        dict(
                            business_id=business,
                            batch_id=identity,
                            entry_id=entry,
                            line_number=number,
                            sheet=value.sheet,
                            source_row=row["row"],
                            source_sha256=extraction["source_sha256"],
                            source_values=Jsonb(row["values"]),
                            created_by=actor,
                        ),
                    )
                self.service._audit(c, actor, business, "journal.proposed", entry)
            return identity

        return self.service._write(
            actor, business, key, "journal.import_proposed", value.model_dump(mode="json"), store
        )

    def read(self, actor: UUID, business: UUID, identity: UUID) -> dict:
        with self.service.database.transaction(actor, business) as c:
            batch = c.execute(
                "SELECT id,extraction_id,document_id,source_sha256,mapping,created_by,created_at "
                "FROM herman.journal_import_batches WHERE business_id=%s AND id=%s",
                (business, identity),
            ).fetchone()
            if batch is None:
                raise NotFound("بسته ورود سند حسابداری موجود نیست")
            entries = c.execute(
                "SELECT DISTINCT e.id,e.entry_date,e.description_fa,d.approved FROM herman.journal_import_sources s "
                "JOIN herman.journal_entries e ON (e.business_id,e.id)=(s.business_id,s.entry_id) "
                "LEFT JOIN herman.journal_decisions d ON (d.business_id,d.entry_id)=(e.business_id,e.id) "
                "WHERE s.business_id=%s AND s.batch_id=%s ORDER BY e.id",
                (business, identity),
            ).fetchall()
            return dict(
                batch=batch, entries=entries, origin=journal_origins(c, business, [e["id"] for e in entries])
            )

    def page(self, actor: UUID, business: UUID, after: UUID | None = None, limit: int = 20) -> list[dict]:
        if not 1 <= limit <= 50:
            raise ValueError("اندازه صفحه باید بین ۱ و ۵۰ باشد")
        with self.service.database.transaction(actor, business) as c:
            return c.execute(
                "SELECT id,extraction_id,document_id,created_at FROM herman.journal_import_batches WHERE business_id=%s "
                "AND (%s::uuid IS NULL OR id>%s) ORDER BY id LIMIT %s",
                (business, after, after, limit),
            ).fetchall()
