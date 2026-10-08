"""Reviewed portfolio inputs and exact cash-flow/chart calculations; no journal inference."""

from __future__ import annotations

import hashlib
from datetime import date
from decimal import localcontext
from typing import Annotated, Literal
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb
from pydantic import Field, model_validator

from src.backend.inventory import EvidenceRef
from src.backend.service import Conflict, NotFound, Service, insert
from src.models import Model, Money

Amount = Annotated[Money, Field(max_digits=28, decimal_places=6)]


class PortfolioFact(Model):
    value: Amount
    evidence: EvidenceRef


FIELDS = (
    "opening_cash",
    "cash_inflows",
    "cash_outflows",
    "revenue",
    "net_income",
    "current_assets",
    "current_liabilities",
)
KPI_LABELS = {
    "revenue": "درآمد",
    "net_income": "سود خالص",
    "net_cash_flow": "جریان نقد خالص",
    "current_ratio": "نسبت جاری",
    "net_margin": "حاشیه سود خالص",
}


class FinancialSnapshot(Model):
    period_start: date
    period_end: date
    currency: Literal["IRR"] = "IRR"
    opening_cash: PortfolioFact
    cash_inflows: PortfolioFact
    cash_outflows: PortfolioFact
    revenue: PortfolioFact
    net_income: PortfolioFact
    current_assets: PortfolioFact
    current_liabilities: PortfolioFact

    @model_validator(mode="after")
    def consistent(self) -> FinancialSnapshot:
        if self.period_end <= self.period_start:
            raise ValueError("پایان دوره باید پس از شروع باشد")
        for name in ("cash_inflows", "cash_outflows", "revenue", "current_assets", "current_liabilities"):
            if getattr(self, name).value < 0:
                raise ValueError("مقدار این قلم نباید منفی باشد: " + name)
        return self


def indicators(value: FinancialSnapshot) -> dict:
    with localcontext() as ctx:
        ctx.prec = 40
        v = {name: getattr(value, name).value for name in FIELDS}
        net = v["cash_inflows"] - v["cash_outflows"]
        closing = v["opening_cash"] + net
        metrics = dict(
            revenue=v["revenue"],
            net_income=v["net_income"],
            net_cash_flow=net,
            current_ratio=v["current_assets"] / v["current_liabilities"]
            if v["current_liabilities"] > 0
            else None,
            net_margin=v["net_income"] / v["revenue"] if v["revenue"] > 0 else None,
        )
        dependencies = dict(
            revenue=["revenue"],
            net_income=["net_income"],
            net_cash_flow=["cash_inflows", "cash_outflows"],
            current_ratio=["current_assets", "current_liabilities"],
            net_margin=["net_income", "revenue"],
        )
        steps = [
            dict(
                key="opening_cash",
                label_fa="نقد ابتدای دوره",
                measure="absolute",
                value=str(v["opening_cash"]),
            ),
            dict(key="cash_inflows", label_fa="ورودی نقد", measure="relative", value=str(v["cash_inflows"])),
            dict(
                key="cash_outflows", label_fa="خروجی نقد", measure="relative", value=str(-v["cash_outflows"])
            ),
            dict(key="closing_cash", label_fa="نقد پایان دوره", measure="total", value=str(closing)),
        ]
        return dict(
            metric_version="portfolio.financial.v1",
            currency="IRR",
            period_start=value.period_start.isoformat(),
            period_end=value.period_end.isoformat(),
            kpis=[
                dict(
                    key=k,
                    label_fa=KPI_LABELS[k],
                    value=str(n) if n is not None else None,
                    unit="fraction" if k in ("current_ratio", "net_margin") else "IRR",
                    status="available" if n is not None else "undefined",
                    reason_fa=None if n is not None else "مخرج صفر است؛ این نسبت قابل محاسبه نیست.",
                    input_fields=dependencies[k],
                )
                for k, n in metrics.items()
            ],
            constants={**{name: str(amount) for name, amount in v.items()}, "closing_cash": str(closing)},
            cashflow_diagram=dict(
                type="waterfall",
                currency="IRR",
                steps=steps,
                input_fields=["opening_cash", "cash_inflows", "cash_outflows"],
            ),
            evidence={name: getattr(value, name).evidence.model_dump(mode="json") for name in FIELDS},
            limitations_fa=[
                "ورودی‌های این نما توسط انسان بررسی شده‌اند؛ از دفتر حسابداری به‌طور خودکار استخراج نشده‌اند.",
                "نقد پایان دوره محاسبه‌شده است و جای تطبیق با مانده واقعی بانک یا صندوق را نمی‌گیرد.",
                "مقادیر نسبت‌ها به صورت کسر هستند؛ برای نمایش درصد حاشیه سود در ۱۰۰ ضرب کنید.",
            ],
        )


class FinancialPortfolio:
    def __init__(self, service: Service) -> None:
        self.service = service

    def _verify(self, c, business: UUID, value: FinancialSnapshot) -> dict:
        hashes = {}
        for name in FIELDS:
            document = getattr(value, name).evidence.document_id
            if str(document) in hashes:
                continue
            row = c.execute(
                "SELECT sha256 FROM herman.documents WHERE business_id=%s AND id=%s", (business, document)
            ).fetchone()
            if row is None:
                raise NotFound("شاهد مالی در این بیزینس موجود نیست")
            try:
                content = (self.service.blob_root / str(business) / row["sha256"]).read_bytes()
            except OSError as exc:
                raise Conflict("فایل شاهد مالی در دسترس نیست") from exc
            if hashlib.sha256(content).hexdigest() != row["sha256"]:
                raise Conflict("فایل شاهد مالی تغییر کرده است")
            hashes[str(document)] = row["sha256"]
        return hashes

    def propose(self, actor: UUID, business: UUID, key: str, value: FinancialSnapshot) -> UUID:
        def store(c):
            self._verify(c, business, value)
            identity = uuid4()
            insert(
                c,
                "financial_snapshots",
                dict(
                    business_id=business,
                    id=identity,
                    period_start=value.period_start,
                    period_end=value.period_end,
                    payload=Jsonb(value.model_dump(mode="json")),
                    created_by=actor,
                ),
            )
            for name in FIELDS:
                ref = getattr(value, name).evidence
                insert(
                    c,
                    "financial_snapshot_sources",
                    dict(
                        business_id=business,
                        snapshot_id=identity,
                        field=name,
                        document_id=ref.document_id,
                        locator=ref.locator,
                        created_by=actor,
                    ),
                )
            return identity

        return self.service._write(
            actor, business, key, "financial_snapshot.proposed", value.model_dump(mode="json"), store
        )

    def decide(
        self, actor: UUID, business: UUID, key: str, identity: UUID, approved: bool, reason_fa: str
    ) -> UUID:
        if not 1 <= len(reason_fa.strip()) <= 2000:
            raise ValueError("دلیل بررسی لازم است")

        def store(c):
            row = c.execute(
                "SELECT payload FROM herman.financial_snapshots WHERE business_id=%s AND id=%s",
                (business, identity),
            ).fetchone()
            if row is None:
                raise NotFound("صورت مالی پیشنهادی موجود نیست")
            if c.execute(
                "SELECT 1 FROM herman.financial_snapshot_decisions WHERE business_id=%s AND snapshot_id=%s",
                (business, identity),
            ).fetchone():
                raise Conflict("تصمیم صورت مالی قبلاً ثبت شده است")
            if approved:
                self._verify(c, business, FinancialSnapshot.model_validate(row["payload"]))
            insert(
                c,
                "financial_snapshot_decisions",
                dict(
                    business_id=business,
                    snapshot_id=identity,
                    approved=approved,
                    reason_fa=reason_fa,
                    created_by=actor,
                ),
            )
            return identity

        return self.service._write(
            actor,
            business,
            key,
            "financial_snapshot.decided",
            dict(id=str(identity), approved=approved, reason_fa=reason_fa),
            store,
            reviewer=True,
        )

    def read(self, actor: UUID, business: UUID, identity: UUID) -> dict:
        with self.service.database.transaction(actor, business) as c:
            row = c.execute(
                "SELECT * FROM herman.financial_snapshots WHERE business_id=%s AND id=%s",
                (business, identity),
            ).fetchone()
            if row is None:
                raise NotFound("صورت مالی پیشنهادی موجود نیست")
            decision = c.execute(
                "SELECT * FROM herman.financial_snapshot_decisions WHERE business_id=%s AND snapshot_id=%s",
                (business, identity),
            ).fetchone()
            return dict(snapshot=row, decision=decision)

    def summary(self, c, business: UUID, effective_date: date) -> dict:
        rows = c.execute(
            "SELECT s.*,d.created_by AS reviewed_by,d.created_at AS reviewed_at "
            "FROM herman.financial_snapshots s JOIN herman.financial_snapshot_decisions d "
            "ON (d.business_id,d.snapshot_id)=(s.business_id,s.id) "
            "WHERE s.business_id=%s AND d.approved AND s.period_end<=%s ORDER BY s.period_end DESC,s.id LIMIT 2",
            (business, effective_date),
        ).fetchall()
        unavailable = [
            dict(key=k, label_fa=label, value=None, status="unavailable") for k, label in KPI_LABELS.items()
        ]
        if not rows:
            return dict(
                status="missing",
                kpis=unavailable,
                cashflow_diagram=None,
                constants={},
                reason_fa="صورت مالی تأییدشده برای این تاریخ موجود نیست.",
            )
        if len(rows) > 1 and rows[0]["period_end"] == rows[1]["period_end"]:
            return dict(
                status="conflict",
                kpis=unavailable,
                cashflow_diagram=None,
                constants={},
                candidate_ids=[str(r["id"]) for r in rows],
                candidates_may_be_truncated=True,
                reason_fa="برای آخرین پایان دوره چند صورت مالی تأیید شده است؛ انتخاب خودکار انجام نمی‌شود.",
            )
        row = rows[0]
        value = FinancialSnapshot.model_validate(row["payload"])
        hashes = self._verify(c, business, value)
        return dict(
            status="confirmed",
            snapshot_id=str(row["id"]),
            reviewed_by=str(row["reviewed_by"]),
            reviewed_at=row["reviewed_at"],
            document_hashes=hashes,
            **indicators(value),
        )
