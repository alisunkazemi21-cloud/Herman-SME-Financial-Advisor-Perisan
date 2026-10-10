"""Immutable, reviewed management reports derived from evidenced journal entries."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import date
from decimal import Decimal, localcontext
from typing import Literal
from uuid import UUID, uuid4

from fastapi.encoders import jsonable_encoder
from psycopg import Connection
from psycopg.types.json import Jsonb
from pydantic import Field, model_validator

from src.backend.inventory import EvidenceRef
from src.backend.journal_sources import journal_origins
from src.backend.journals import Code, Journals
from src.backend.portfolio import KPI_LABELS, indicator_values
from src.backend.service import Conflict, NotFound, Service, canonical, insert
from src.models import Model

MAX_LINES = 10000
Category = Literal[
    "cash",
    "current_asset",
    "noncurrent_asset",
    "current_liability",
    "noncurrent_liability",
    "equity",
    "revenue",
    "expense",
]
KINDS = {
    "cash": "asset",
    "current_asset": "asset",
    "noncurrent_asset": "asset",
    "current_liability": "liability",
    "noncurrent_liability": "liability",
    "equity": "equity",
    "revenue": "revenue",
    "expense": "expense",
}


class MappingInput(Model):
    title_fa: str = Field(min_length=3, max_length=200)
    accounts: dict[Code, Category] = Field(min_length=1, max_length=1000)
    evidence: EvidenceRef


class ReviewInput(Model):
    approved: bool
    reviewed_values: Literal[True]
    reason_fa: str = Field(min_length=3, max_length=2000)


class ReportReview(ReviewInput):
    scope_confirmed: bool = False

    @model_validator(mode="after")
    def reviewed_scope(self) -> ReportReview:
        if self.approved and not self.scope_confirmed:
            raise ValueError("برای تأیید گزارش، دامنه حساب‌ها و کامل بودن ثبت‌های دوره باید بررسی شود")
        return self


class ReportInput(Model):
    mapping_id: UUID
    period_start: date
    period_end: date
    supersedes: UUID | None = None

    @model_validator(mode="after")
    def ordered(self) -> ReportInput:
        if self.period_end < self.period_start:
            raise ValueError("پایان دوره پیش از شروع است")
        return self


def digest(payload: dict) -> str:
    return hashlib.sha256(canonical(payload).encode()).hexdigest()


def bounded(payload: dict, maximum: int) -> dict:
    result = jsonable_encoder(payload)
    if len(canonical(result).encode()) > maximum:
        raise Conflict("حجم گزارش بیش از حد است؛ پردازش دسته‌ای لازم است")
    return result


def calculate(manifest: dict) -> dict:
    """All values come from immutable selected lines; no label inference or LLM arithmetic."""
    policy = manifest["mapping"]["payload"]["accounts"]
    start, end = date.fromisoformat(manifest["period_start"]), date.fromisoformat(manifest["period_end"])
    dates = {entry["id"]: date.fromisoformat(entry["entry_date"]) for entry in manifest["entries"]}
    with localcontext() as ctx:
        ctx.prec = 60
        balances = {
            code: dict(opening=Decimal(0), debit=Decimal(0), credit=Decimal(0), closing=Decimal(0))
            for code in policy
        }
        cash_nets: dict[str, Decimal] = defaultdict(Decimal)
        for line in manifest["lines"]:
            amount = Decimal(line["amount"])
            signed = amount if line["side"] == "debit" else -amount
            row = balances[line["account_code"]]
            row["closing"] += signed
            if dates[line["entry_id"]] < start:
                row["opening"] += signed
            else:
                row[line["side"]] += amount
                if policy[line["account_code"]] == "cash":
                    cash_nets[line["entry_id"]] += signed

        def total(categories: set[str], key: str) -> Decimal:
            return sum((row[key] for code, row in balances.items() if policy[code] in categories), Decimal(0))

        revenue = total({"revenue"}, "credit") - total({"revenue"}, "debit")
        expense = total({"expense"}, "debit") - total({"expense"}, "credit")
        values = dict(
            opening_cash=total({"cash"}, "opening"),
            cash_inflows=sum((n for n in cash_nets.values() if n > 0), Decimal(0)),
            cash_outflows=-sum((n for n in cash_nets.values() if n < 0), Decimal(0)),
            revenue=revenue,
            net_income=revenue - expense,
            current_assets=total({"cash", "current_asset"}, "closing"),
            current_liabilities=-total({"current_liability"}, "closing"),
        )
        financial = indicator_values(values, start, end, precision=60)
        if Decimal(financial["constants"]["closing_cash"]) != total({"cash"}, "closing"):
            raise ValueError("تطبیق مانده نقد گزارش نامعتبر است")
        financial["metric_version"] = "journal.financial.v1"
        financial["cashflow_diagram"]["basis"] = "net_cash_per_journal"
        financial["cashflow_diagram"]["steps"][1]["label_fa"] = "ورودی نقد خالص اسناد"
        financial["cashflow_diagram"]["steps"][2]["label_fa"] = "خروجی نقد خالص اسناد"
        field_categories = dict(
            opening_cash={"cash"},
            cash_inflows={"cash"},
            cash_outflows={"cash"},
            revenue={"revenue"},
            net_income={"revenue", "expense"},
            current_assets={"cash", "current_asset"},
            current_liabilities={"current_liability"},
        )
        financial["field_accounts"] = {
            name: sorted(code for code, category in policy.items() if category in categories)
            for name, categories in field_categories.items()
        }
        financial["limitations_fa"] = [
            "اعداد فقط از ثبت‌های تأییدشده در رسید گزارش و نگاشت بررسی‌شده به دست آمده‌اند.",
            "ورودی و خروجی نقد، جمع خالص حرکت نقد در هر سند است؛ اسناد تجمیعی جای ریز گردش بانک را نمی‌گیرند.",
            "درآمد و سود از گردش حساب‌ها محاسبه شده‌اند؛ ثبت‌های اختتامیه یا داده ناقص می‌توانند این مقادیر را تغییر دهند.",
            "نگاشت نقد در این گزارش شامل حساب‌های نقد جاری منتخب است؛ این نما صورت مالی قانونی یا تأیید انطباق با استانداردها نیست.",
            "نسبت‌ها به صورت کسر هستند؛ مخرج غیرمثبت نتیجه تعریف‌نشده دارد.",
        ]
        return dict(
            financial=financial,
            trial_balance=[
                dict(code=code, category=policy[code], **{k: str(v) for k, v in row.items()})
                for code, row in sorted(balances.items())
            ],
            source_entries=len(manifest["entries"]),
            source_lines=len(manifest["lines"]),
        )


class JournalReports:
    def __init__(self, service: Service) -> None:
        self.service = service
        self.journals = Journals(service)

    @staticmethod
    def _accounts(c: Connection, business: UUID, mapping: MappingInput) -> list[dict]:
        rows = c.execute(
            'SELECT code,name_fa,kind FROM herman.journal_accounts WHERE business_id=%s ORDER BY code COLLATE "C" LIMIT 1001',
            (business,),
        ).fetchall()
        if len(rows) > 1000 or {r["code"] for r in rows} != set(mapping.accounts):
            raise Conflict("نگاشت باید تمام حساب‌های فعلی بیزینس را پوشش دهد؛ نگاشت جدید لازم است")
        if any(KINDS[mapping.accounts[r["code"]]] != r["kind"] for r in rows):
            raise ValueError("دسته نگاشت با نوع حساب سازگار نیست")
        if "cash" not in mapping.accounts.values():
            raise ValueError("برای گزارش نقد، حداقل یک حساب نقد جاری باید مشخص شود")
        return rows

    def mapping(self, actor: UUID, business: UUID, key: str, value: MappingInput) -> UUID:
        def store(c: Connection) -> UUID:
            self._accounts(c, business, value)
            self.journals._verify(c, business, {value.evidence.document_id})
            identity = uuid4()
            insert(
                c,
                "journal_mappings",
                dict(
                    business_id=business,
                    id=identity,
                    payload=Jsonb(value.model_dump(mode="json")),
                    **value.evidence.model_dump(),
                    created_by=actor,
                ),
            )
            return identity

        return self.service._write(
            actor, business, key, "journal.mapping_proposed", value.model_dump(mode="json"), store
        )

    @staticmethod
    def _mapping(c: Connection, business: UUID, identity: UUID) -> dict:
        row = c.execute(
            "SELECT m.id,m.payload,m.created_by,m.created_at,d.approved,d.created_by AS reviewed_by,"
            "d.created_at AS reviewed_at,d.reason_fa FROM herman.journal_mappings m LEFT JOIN herman.journal_mapping_decisions d "
            "ON (d.business_id,d.mapping_id)=(m.business_id,m.id) WHERE m.business_id=%s AND m.id=%s",
            (business, identity),
        ).fetchone()
        if row is None:
            raise NotFound("نگاشت حساب در این بیزینس موجود نیست")
        return row

    def read_mapping(self, actor: UUID, business: UUID, identity: UUID) -> dict:
        with self.service.database.transaction(actor, business) as c:
            return self._mapping(c, business, identity)

    def review_mapping(
        self, actor: UUID, business: UUID, key: str, identity: UUID, value: ReviewInput
    ) -> UUID:
        def store(c: Connection) -> UUID:
            row = self._mapping(c, business, identity)
            if value.approved:
                mapping = MappingInput.model_validate(row["payload"])
                self._accounts(c, business, mapping)
                self.journals._verify(c, business, {mapping.evidence.document_id})
            insert(
                c,
                "journal_mapping_decisions",
                dict(business_id=business, mapping_id=identity, **value.model_dump(), created_by=actor),
            )
            return identity

        return self.service._write(
            actor,
            business,
            key,
            "journal.mapping_reviewed",
            dict(id=str(identity), **value.model_dump()),
            store,
            reviewer=True,
        )

    def create(self, actor: UUID, business: UUID, key: str, value: ReportInput) -> UUID:
        def store(c: Connection) -> UUID:
            if value.supersedes:
                previous = self._load(c, business, value.supersedes, verify=False)
                if (
                    not previous["approved"]
                    or previous["period_start"] != value.period_start
                    or previous["period_end"] != value.period_end
                    or self._replacement(c, business, value.supersedes)
                ):
                    raise Conflict("گزارش جایگزین باید به آخرین رسید تأییدشده همان دوره ارجاع دهد")
            mapping = self._mapping(c, business, value.mapping_id)
            if not mapping["approved"]:
                raise Conflict("نگاشت حساب‌ها باید پیش از ساخت گزارش تأیید شود")
            policy = MappingInput.model_validate(mapping["payload"])
            accounts = self._accounts(c, business, policy)
            entries = c.execute(
                "SELECT e.id,e.entry_date,e.event_fingerprint,d.created_by AS reviewed_by,d.created_at AS reviewed_at "
                "FROM herman.journal_entries e JOIN herman.journal_decisions d ON (d.business_id,d.entry_id)=(e.business_id,e.id) "
                "WHERE e.business_id=%s AND e.entry_date<=%s AND d.approved ORDER BY e.id LIMIT 5001",
                (business, value.period_end),
            ).fetchall()
            if not entries:
                raise Conflict("ثبت تأییدشده‌ای برای گزارش وجود ندارد")
            if len(entries) > 5000:
                raise Conflict("تعداد اسناد بیش از حد گزارش هم‌زمان است؛ پردازش دسته‌ای لازم است")
            lines = c.execute(
                "SELECT entry_id,line_number,account_code,side,amount::text AS amount,document_id,locator "
                "FROM herman.journal_lines WHERE business_id=%s AND entry_id=ANY(%s) ORDER BY entry_id,line_number LIMIT %s",
                (business, [entry["id"] for entry in entries], MAX_LINES + 1),
            ).fetchall()
            if len(lines) > MAX_LINES:
                raise Conflict("تعداد سطرها بیش از حد گزارش است؛ پردازش دسته‌ای لازم است")
            documents = {line["document_id"] for line in lines} | {policy.evidence.document_id}
            if len(documents) > 1000:
                raise Conflict("تعداد شواهد بیش از حد گزارش هم‌زمان است؛ پردازش دسته‌ای لازم است")
            hashes = self.journals._verify(c, business, documents)
            manifest = bounded(
                dict(
                    version="journal.report.inputs.v1",
                    **value.model_dump(mode="json"),
                    mapping=mapping,
                    accounts=accounts,
                    entries=entries,
                    lines=lines,
                    import_provenance=journal_origins(c, business, [entry["id"] for entry in entries]),
                    document_hashes=hashes,
                ),
                8 * 1024 * 1024,
            )
            result = bounded(calculate(manifest), 512 * 1024)
            identity = uuid4()
            insert(
                c,
                "journal_reports",
                dict(
                    business_id=business,
                    id=identity,
                    **value.model_dump(),
                    manifest=Jsonb(manifest),
                    result=Jsonb(result),
                    input_sha256=digest(manifest),
                    result_sha256=digest(result),
                    created_by=actor,
                ),
            )
            return identity

        return self.service._write(
            actor, business, key, "journal.report_created", value.model_dump(mode="json"), store
        )

    def _load(self, c: Connection, business: UUID, identity: UUID, verify: bool = True) -> dict:
        row = c.execute(
            "SELECT r.*,d.approved,d.scope_confirmed,d.created_by AS reviewed_by,d.created_at AS reviewed_at,d.reason_fa "
            "FROM herman.journal_reports r LEFT JOIN herman.journal_report_decisions d ON (d.business_id,d.report_id)=(r.business_id,r.id) "
            "WHERE r.business_id=%s AND r.id=%s",
            (business, identity),
        ).fetchone()
        if row is None:
            raise NotFound("گزارش دفتر در این بیزینس موجود نیست")
        if digest(row["manifest"]) != row["input_sha256"] or digest(row["result"]) != row["result_sha256"]:
            raise Conflict("رسید گزارش تغییر کرده است")
        if verify:
            hashes = self.journals._verify(c, business, {UUID(k) for k in row["manifest"]["document_hashes"]})
            if hashes != row["manifest"]["document_hashes"]:
                raise Conflict("شواهد گزارش با رسید ثبت‌شده یکسان نیست")
        return row

    @staticmethod
    def freshness(c: Connection, business: UUID, row: dict) -> dict:
        current = c.execute(
            "SELECT e.id FROM herman.journal_entries e JOIN herman.journal_decisions d "
            "ON (d.business_id,d.entry_id)=(e.business_id,e.id) WHERE e.business_id=%s AND e.entry_date<=%s AND d.approved LIMIT 5001",
            (business, row["period_end"]),
        ).fetchall()
        saved = {entry["id"] for entry in row["manifest"]["entries"]}
        return dict(
            stale={str(r["id"]) for r in current} != saved,
            saved_entries=len(saved),
            current_entries_at_least=len(current),
            count_limited=len(current) > 5000,
        )

    def read(self, actor: UUID, business: UUID, identity: UUID) -> dict:
        with self.service.database.transaction(actor, business) as c:
            row = self._load(c, business, identity)
            row["freshness"] = self.freshness(c, business, row)
            row["superseded_by"] = self._replacement(c, business, identity)
            return row

    @staticmethod
    def _replacement(c: Connection, business: UUID, identity: UUID) -> UUID | None:
        row = c.execute(
            "SELECT report_id FROM herman.journal_report_decisions WHERE business_id=%s AND supersedes=%s AND approved",
            (business, identity),
        ).fetchone()
        return row["report_id"] if row else None

    def review(self, actor: UUID, business: UUID, key: str, identity: UUID, value: ReportReview) -> UUID:
        def store(c: Connection) -> UUID:
            row = self._load(c, business, identity, verify=value.approved)
            if value.approved and self.freshness(c, business, row)["stale"]:
                raise Conflict("ثبت‌های دوره تغییر کرده‌اند؛ گزارش تازه تهیه کنید")
            insert(
                c,
                "journal_report_decisions",
                dict(business_id=business, report_id=identity, **value.model_dump(), created_by=actor),
            )
            return identity

        return self.service._write(
            actor,
            business,
            key,
            "journal.report_reviewed",
            dict(id=str(identity), **value.model_dump()),
            store,
            reviewer=True,
        )

    def summary(self, c: Connection, business: UUID, identity: UUID) -> dict:
        row = self._load(c, business, identity)
        if not row["approved"]:
            raise Conflict("گزارش دفتر هنوز تأیید نشده است")
        freshness = self.freshness(c, business, row)
        replacement = self._replacement(c, business, identity)
        metadata = dict(
            source_kind="journal_report",
            report_id=str(identity),
            mapping_id=str(row["mapping_id"]),
            input_sha256=row["input_sha256"],
            result_sha256=row["result_sha256"],
            reviewed_by=str(row["reviewed_by"]),
            reviewed_at=row["reviewed_at"],
            period_start=row["period_start"],
            period_end=row["period_end"],
            freshness=freshness,
            source_entries=row["result"]["source_entries"],
            source_lines=row["result"]["source_lines"],
            superseded_by=str(replacement) if replacement else None,
        )
        if freshness["stale"] or replacement:
            return dict(
                **metadata,
                status="superseded" if replacement else "stale",
                constants={},
                cashflow_diagram=None,
                kpis=[
                    dict(key=k, label_fa=label, value=None, status="unavailable")
                    for k, label in KPI_LABELS.items()
                ],
                reason_fa="این رسید با گزارش تأییدشده جدید جایگزین شده است."
                if replacement
                else "ثبت‌های تأییدشده دوره تغییر کرده‌اند؛ برای استفاده در مشاوره گزارش جدید لازم است.",
            )
        return {**metadata, "status": "confirmed", **row["result"]["financial"]}

    def page(
        self,
        actor: UUID,
        business: UUID,
        resource: Literal["mappings", "reports"],
        after: UUID | None = None,
        limit: int = 20,
    ) -> list[dict]:
        if not 1 <= limit <= 50:
            raise ValueError("اندازه صفحه باید بین ۱ و ۵۰ باشد")
        if resource == "mappings":
            query = "SELECT id,created_at,payload->>'title_fa' AS title_fa FROM herman.journal_mappings "
        elif resource == "reports":
            query = "SELECT id,created_at,mapping_id,period_start,period_end,input_sha256,result_sha256 FROM herman.journal_reports "
        else:
            raise ValueError("منبع نامعتبر است")
        with self.service.database.transaction(actor, business) as c:
            return c.execute(
                query + "WHERE business_id=%s AND (%s::uuid IS NULL OR id>%s) ORDER BY id LIMIT %s",
                (business, after, after, limit),
            ).fetchall()
