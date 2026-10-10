"""Evidence-backed tenant journals and exact trial balances; approvals remain human actions."""

from __future__ import annotations

import hashlib
from datetime import date
from decimal import Decimal, localcontext
from typing import Annotated, Literal
from uuid import UUID, uuid4

from psycopg import Connection
from pydantic import Field, model_validator

from src.backend.inventory import EvidenceRef
from src.backend.service import Conflict, NotFound, Service, insert
from src.ingestion.normalizer import parse_jalali
from src.models import Model, Money

Code = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,32}$")]
Amount = Annotated[Money, Field(gt=0, max_digits=28, decimal_places=6)]


class AccountInput(Model):
    code: Code
    name_fa: str = Field(min_length=1, max_length=200)
    kind: Literal["asset", "liability", "equity", "revenue", "expense"]


class JournalLine(Model):
    account_code: Code
    side: Literal["debit", "credit"]
    amount: Amount
    evidence: EvidenceRef


class JournalDates(Model):
    entry_date: date
    jalali_date: str = Field(max_length=10)
    description_fa: str = Field(min_length=3, max_length=2000)

    @model_validator(mode="after")
    def dates_match(self) -> JournalDates:
        if parse_jalali(self.jalali_date) != self.entry_date:
            raise ValueError("تاریخ شمسی و میلادی سند یکسان نیستند")
        return self


class JournalInput(JournalDates):
    currency: Literal["IRR"] = "IRR"
    lines: list[JournalLine] = Field(min_length=2, max_length=100)

    @model_validator(mode="after")
    def balanced(self) -> JournalInput:
        if len({line.account_code for line in self.lines}) != len(self.lines):
            raise ValueError("هر حساب در یک سند فقط یک سطر دارد")
        with localcontext() as ctx:
            ctx.prec = 40
            net = sum(
                (line.amount if line.side == "debit" else -line.amount for line in self.lines), Decimal(0)
            )
        if net != 0:
            raise ValueError("جمع بدهکار و بستانکار برابر نیست")
        return self


class JournalDecision(Model):
    approved: bool
    reviewed_values: Literal[True]
    reason_fa: str = Field(min_length=3, max_length=2000)
    duplicate_resolution: Literal["same_event", "distinct_event"] | None = None

    @model_validator(mode="after")
    def consistent(self) -> JournalDecision:
        if self.approved and self.duplicate_resolution == "same_event":
            raise ValueError("ثبت تکراری همان رویداد نباید تأیید شود")
        return self


def fingerprint(value: JournalInput) -> str:
    parts = [value.entry_date.isoformat(), value.currency]
    parts.extend(
        f"{line.account_code}:{line.side}:{line.amount:.6f}"
        for line in sorted(value.lines, key=lambda line: line.account_code)
    )
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


class Journals:
    def __init__(self, service: Service) -> None:
        self.service = service

    def account(self, actor: UUID, business: UUID, key: str, value: AccountInput) -> UUID:
        def store(c: Connection) -> UUID:
            identity = uuid4()
            insert(
                c,
                "journal_accounts",
                dict(business_id=business, id=identity, **value.model_dump(), created_by=actor),
            )
            return identity

        return self.service._write(actor, business, key, "journal.account_created", value.model_dump(), store)

    def accounts(self, actor: UUID, business: UUID, after: str = "", limit: int = 50) -> list[dict]:
        if not 1 <= limit <= 100 or len(after) > 32:
            raise ValueError("اندازه صفحه یا نشانگر حساب نامعتبر است")
        with self.service.database.transaction(actor, business) as c:
            return c.execute(
                "SELECT code,name_fa,kind,id FROM herman.journal_accounts WHERE business_id=%s "
                'AND code COLLATE "C">%s ORDER BY code COLLATE "C" LIMIT %s',
                (business, after, limit),
            ).fetchall()

    def _verify(self, c: Connection, business: UUID, documents: set[UUID]) -> dict[str, str]:
        hashes = {}
        for identity in sorted(documents, key=str):
            row = c.execute(
                "SELECT sha256 FROM herman.documents WHERE business_id=%s AND id=%s", (business, identity)
            ).fetchone()
            if row is None:
                raise NotFound("شاهد سند حسابداری در این بیزینس موجود نیست")
            try:
                content = (self.service.blob_root / str(business) / row["sha256"]).read_bytes()
            except OSError as exc:
                raise Conflict("فایل شاهد سند در دسترس نیست") from exc
            if hashlib.sha256(content).hexdigest() != row["sha256"]:
                raise Conflict("فایل شاهد سند تغییر کرده است")
            hashes[str(identity)] = row["sha256"]
        return hashes

    def _store(
        self, c: Connection, actor: UUID, business: UUID, value: JournalInput, reversal_of: UUID | None = None
    ) -> UUID:
        self._verify(c, business, {line.evidence.document_id for line in value.lines})
        identity = uuid4()
        insert(
            c,
            "journal_entries",
            dict(
                business_id=business,
                id=identity,
                entry_date=value.entry_date,
                jalali_date=value.jalali_date,
                currency=value.currency,
                description_fa=value.description_fa,
                event_fingerprint=fingerprint(value),
                reversal_of=reversal_of,
                created_by=actor,
            ),
        )
        for number, line in enumerate(value.lines, 1):
            insert(
                c,
                "journal_lines",
                dict(
                    business_id=business,
                    entry_id=identity,
                    line_number=number,
                    account_code=line.account_code,
                    side=line.side,
                    amount=line.amount,
                    **line.evidence.model_dump(),
                    created_by=actor,
                ),
            )
        return identity

    def propose(self, actor: UUID, business: UUID, key: str, value: JournalInput) -> UUID:
        return self.service._write(
            actor,
            business,
            key,
            "journal.proposed",
            value.model_dump(mode="json"),
            lambda c: self._store(c, actor, business, value),
        )

    @staticmethod
    def _entry(c: Connection, business: UUID, identity: UUID) -> tuple[dict, list[dict]]:
        row = c.execute(
            "SELECT id,entry_date,jalali_date,currency,description_fa,event_fingerprint,"
            "reversal_of,created_by,created_at FROM herman.journal_entries WHERE business_id=%s AND id=%s",
            (business, identity),
        ).fetchone()
        if row is None:
            raise NotFound("سند حسابداری موجود نیست")
        lines = c.execute(
            "SELECT l.line_number,l.account_code,a.name_fa,l.side,l.amount::text AS amount,"
            "l.document_id,l.locator FROM herman.journal_lines l JOIN herman.journal_accounts a "
            "ON (a.business_id,a.code)=(l.business_id,l.account_code) "
            "WHERE l.business_id=%s AND entry_id=%s ORDER BY line_number",
            (business, identity),
        ).fetchall()
        return row, lines

    def decide(self, actor: UUID, business: UUID, key: str, identity: UUID, value: JournalDecision) -> UUID:
        def store(c: Connection) -> UUID:
            _, lines = self._entry(c, business, identity)
            if value.approved:
                self._verify(c, business, {line["document_id"] for line in lines})
            insert(
                c,
                "journal_decisions",
                dict(business_id=business, entry_id=identity, **value.model_dump(), created_by=actor),
            )
            return identity

        return self.service._write(
            actor,
            business,
            key,
            "journal.reviewed",
            dict(entry_id=str(identity), **value.model_dump()),
            store,
            reviewer=True,
        )

    def reverse(self, actor: UUID, business: UUID, key: str, original: UUID, value: JournalDates) -> UUID:
        def store(c: Connection) -> UUID:
            row, lines = self._entry(c, business, original)
            if (
                row["reversal_of"]
                or value.entry_date < row["entry_date"]
                or not c.execute(
                    "SELECT 1 FROM herman.journal_decisions WHERE business_id=%s AND entry_id=%s AND approved",
                    (business, original),
                ).fetchone()
            ):
                raise Conflict("فقط سند اصلی تأییدشده در همان تاریخ یا بعد از آن قابل برگشت است")
            if c.execute(
                "SELECT 1 FROM herman.journal_decisions WHERE business_id=%s AND reversal_of=%s AND approved",
                (business, original),
            ).fetchone():
                raise Conflict("سند قبلاً برگشت داده شده است")
            proposal = JournalInput(
                **value.model_dump(),
                lines=[
                    dict(
                        account_code=line["account_code"],
                        side="credit" if line["side"] == "debit" else "debit",
                        amount=line["amount"],
                        evidence=dict(document_id=line["document_id"], locator=line["locator"]),
                    )
                    for line in lines
                ],
            )
            return self._store(c, actor, business, proposal, original)

        return self.service._write(
            actor,
            business,
            key,
            "journal.reversal_proposed",
            dict(original=str(original), **value.model_dump(mode="json")),
            store,
        )

    def read(self, actor: UUID, business: UUID, identity: UUID) -> dict:
        with self.service.database.transaction(actor, business) as c:
            row, lines = self._entry(c, business, identity)
            hashes = self._verify(c, business, {line["document_id"] for line in lines})
            decision = c.execute(
                "SELECT approved,reviewed_values,reason_fa,duplicate_resolution,created_by,created_at "
                "FROM herman.journal_decisions WHERE business_id=%s AND entry_id=%s",
                (business, identity),
            ).fetchone()
            matches = c.execute(
                "SELECT e.id,d.approved FROM herman.journal_entries e LEFT JOIN herman.journal_decisions d "
                "ON (d.business_id,d.entry_id)=(e.business_id,e.id) WHERE e.business_id=%s "
                "AND e.event_fingerprint=%s AND e.id<>%s ORDER BY e.id LIMIT 21",
                (business, row["event_fingerprint"], identity),
            ).fetchall()
            reversals = c.execute(
                "SELECT e.id,d.approved FROM herman.journal_entries e LEFT JOIN herman.journal_decisions d "
                "ON (d.business_id,d.entry_id)=(e.business_id,e.id) WHERE e.business_id=%s "
                "AND e.reversal_of=%s ORDER BY e.id LIMIT 21",
                (business, identity),
            ).fetchall()
            state = "در انتظار بررسی" if decision is None else "تأییدشده" if decision["approved"] else "ردشده"
            return dict(
                entry=row,
                lines=lines,
                decision=decision,
                evidence_sha256=hashes,
                duplicate_candidates=matches[:20],
                duplicates_truncated=len(matches) > 20,
                reversals=reversals[:20],
                reversals_truncated=len(reversals) > 20,
                status_fa=state,
                explanation_fa=f"سند {row['jalali_date']}: {row['description_fa']}؛ {state}. "
                "جمع بدهکار و بستانکار برابر است. جهت ثبت به‌تنهایی به معنی ورود یا خروج پول نیست.",
            )

    def page(self, actor: UUID, business: UUID, after: UUID | None = None, limit: int = 50) -> list[dict]:
        if not 1 <= limit <= 100:
            raise ValueError("اندازه صفحه باید بین ۱ و ۱۰۰ باشد")
        with self.service.database.transaction(actor, business) as c:
            return c.execute(
                "SELECT e.id,e.entry_date,e.jalali_date,e.description_fa,e.reversal_of,d.approved "
                "FROM herman.journal_entries e LEFT JOIN herman.journal_decisions d "
                "ON (d.business_id,d.entry_id)=(e.business_id,e.id) WHERE e.business_id=%s "
                "AND (%s::uuid IS NULL OR e.id>%s) ORDER BY e.id LIMIT %s",
                (business, after, after, limit),
            ).fetchall()

    def trial_balance(self, actor: UUID, business: UUID, start: date, end: date) -> dict:
        if end < start:
            raise ValueError("پایان دوره پیش از شروع است")
        with self.service.database.transaction(actor, business) as c:
            documents = c.execute(
                "SELECT DISTINCT l.document_id FROM herman.journal_lines l "
                "JOIN herman.journal_entries e ON (e.business_id,e.id)=(l.business_id,l.entry_id) "
                "JOIN herman.journal_decisions d ON (d.business_id,d.entry_id)=(e.business_id,e.id) "
                "WHERE e.business_id=%s AND e.entry_date<=%s AND d.approved LIMIT 1001",
                (business, end),
            ).fetchall()
            if len(documents) > 1000:
                raise Conflict("دامنه شواهد بیش از حد است؛ گزارش دفتر به پردازش دسته‌ای نیاز دارد")
            hashes = self._verify(c, business, {row["document_id"] for row in documents})
            rows = c.execute(
                "WITH totals AS (SELECT l.account_code,"
                "coalesce(sum(CASE WHEN l.side='debit' THEN l.amount ELSE -l.amount END) FILTER(WHERE e.entry_date<%s),0) opening,"
                "coalesce(sum(l.amount) FILTER(WHERE e.entry_date>=%s AND l.side='debit'),0) debit,"
                "coalesce(sum(l.amount) FILTER(WHERE e.entry_date>=%s AND l.side='credit'),0) credit "
                "FROM herman.journal_lines l JOIN herman.journal_entries e ON (e.business_id,e.id)=(l.business_id,l.entry_id) "
                "JOIN herman.journal_decisions d ON (d.business_id,d.entry_id)=(e.business_id,e.id) "
                "WHERE e.business_id=%s AND e.entry_date<=%s AND d.approved GROUP BY l.account_code) "
                "SELECT a.code,a.name_fa,a.kind,coalesce(t.opening,0)::text AS opening_net,"
                "coalesce(t.debit,0)::text AS period_debit,coalesce(t.credit,0)::text AS period_credit,"
                "(coalesce(t.opening,0)+coalesce(t.debit,0)-coalesce(t.credit,0))::text AS closing_net "
                "FROM herman.journal_accounts a LEFT JOIN totals t ON t.account_code=a.code WHERE a.business_id=%s "
                'ORDER BY a.code COLLATE "C" LIMIT 1001',
                (start, start, start, business, end, business),
            ).fetchall()
            if len(rows) > 1000:
                raise Conflict("تعداد حساب‌ها بیش از حد گزارش است؛ گزارش دسته‌ای لازم است")
            totals = c.execute(
                "SELECT count(DISTINCT e.id) AS approved_entries,"
                "coalesce(sum(l.amount) FILTER(WHERE l.side='debit' AND e.entry_date>=%s),0)::text AS period_debit,"
                "coalesce(sum(l.amount) FILTER(WHERE l.side='credit' AND e.entry_date>=%s),0)::text AS period_credit "
                "FROM herman.journal_entries e JOIN herman.journal_decisions d ON (d.business_id,d.entry_id)=(e.business_id,e.id) "
                "JOIN herman.journal_lines l ON (l.business_id,l.entry_id)=(e.business_id,e.id) "
                "WHERE e.business_id=%s AND e.entry_date<=%s AND d.approved",
                (start, start, business, end),
            ).fetchone()
            return dict(
                version="journal.trial_balance.v1",
                currency="IRR",
                start=start,
                end=end,
                accounts=rows,
                totals=totals,
                evidence_sha256=hashes,
                evidence_verified=True,
                limitations_fa=[
                    "مانده خالص مثبت بدهکار و منفی بستانکار است.",
                    "این گزارش فقط ثبت‌های تأییدشده موجود را پوشش می‌دهد و کامل بودن دفتر یا وضعیت واقعی کسب‌وکار را اثبات نمی‌کند.",
                    "گزارش بر اساس تاریخ سند و تأییدهای موجود در لحظه خواندن است؛ ثبت با تاریخ گذشته می‌تواند گزارش آینده را تغییر دهد.",
                    "این تراز آزمایشی است و جای صورت مالی قانونی یا تطبیق بانک را نمی‌گیرد.",
                ],
            )
