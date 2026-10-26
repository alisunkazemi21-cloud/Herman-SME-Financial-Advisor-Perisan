"""Reviewed catalog revisions and bounded, dated presentation reads."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from src.backend.inventory import EvidenceRef, Item, PositiveQuantity
from src.backend.item_selection import select_item_labels
from src.backend.pack_selection import pack_timeline as pack_timeline
from src.backend.service import Conflict, NotFound, Service, insert
from src.models import Model


class PackProposal(Model):
    id: UUID
    item_id: UUID
    predecessor_id: UUID
    base_quantity: PositiveQuantity
    evidence: EvidenceRef


class PackDecision(Model):
    approved: bool
    reason_fa: str = Field(min_length=1, max_length=2000)
    effective_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def no_rejected_activation(self) -> "PackDecision":
        if not self.approved and self.effective_at is not None:
            raise ValueError("نسخهٔ ردشده زمان فعال‌سازی ندارد")
        return self


class ItemProposal(Model):
    id: UUID
    item_id: UUID
    predecessor_id: UUID
    sku: str = Field(min_length=1, max_length=100)
    name_fa: str = Field(min_length=1, max_length=200)
    evidence: EvidenceRef

    @model_validator(mode="after")
    def meaningful_labels(self) -> "ItemProposal":
        if not self.sku.strip() or not self.name_fa.strip():
            raise ValueError("نام و شناسه کالا نباید خالی باشند")
        return self


class ItemDecision(PackDecision):
    pass


def _definition_sql(kind: Literal["item", "pack"]) -> str:
    if kind not in ("item", "pack"):
        raise ValueError("نوع نسخهٔ کاتالوگ نامعتبر است")
    common = (
        "SELECT p.*,d.approved,d.actor_id AS reviewed_by,d.reason_fa,d.decided_at,d.effective_at,"
        "s.definition_id AS successor_id,")
    if kind == "item":
        return common + (
            "lower(a.validity) AS valid_from,upper(a.validity) AS valid_to,"
            "(a.definition_id IS NOT NULL) AS published FROM herman.item_definitions p "
            "LEFT JOIN herman.item_decisions d ON (d.business_id,d.definition_id)=(p.business_id,p.id) "
            "LEFT JOIN herman.item_decisions s ON s.business_id=p.business_id AND s.predecessor_id=p.id AND s.approved "
            "LEFT JOIN herman.item_alias_periods a ON (a.business_id,a.definition_id)=(p.business_id,p.id) ")
    return common + (
        "d.effective_at AS valid_from,s.effective_at AS valid_to,"
        "(p.baseline OR COALESCE(d.approved,false)) AS published,o.observed_at,o.origin AS observation_origin "
        "FROM herman.pack_definitions p "
        "LEFT JOIN herman.pack_decisions d ON (d.business_id,d.definition_id)=(p.business_id,p.id) "
        "LEFT JOIN herman.pack_decisions s ON s.business_id=p.business_id AND s.predecessor_id=p.id AND s.approved "
        "JOIN herman.pack_definition_observations o ON (o.business_id,o.definition_id)=(p.business_id,p.id) ")


def _historical_use_detail() -> dict:
    return dict(historical_usage_status="not_evaluated",
                explanation_fa="تعریف بسته برای نمایش کاتالوگ است؛ پشتیبانی آن برای مصرف‌های گذشته جداگانه بررسی می‌شود.")


class Catalog:
    def __init__(self, service: Service):
        self.service = service

    @staticmethod
    def _item(c, business: UUID, item: UUID) -> dict:
        row = c.execute("SELECT * FROM herman.items WHERE business_id=%s AND id=%s", (business, item)).fetchone()
        if row is None:
            raise NotFound("کالا در این بیزینس موجود نیست")
        return row

    @staticmethod
    def _instant(c, effective_at: datetime | None) -> datetime:
        return effective_at if effective_at is not None else c.execute("SELECT clock_timestamp() AS at").fetchone()["at"]

    def items(self, actor: UUID, business: UUID, effective_at: datetime | None = None,
              after: UUID | None = None, limit: int = 50) -> dict:
        if not 1 <= limit <= 100:
            raise ValueError("اندازهٔ صفحه نامعتبر است")
        with self.service.database.transaction(actor, business) as c:
            moment = self._instant(c, effective_at)
            rows = c.execute("SELECT * FROM herman.items WHERE business_id=%s "
                             "AND (%s::uuid IS NULL OR id>%s) ORDER BY id LIMIT %s",
                             (business, after, after, limit + 1)).fetchall()
            page = rows[:limit]
            state = select_item_labels(c, business, [row["id"] for row in page], moment)
            labels = {label.item_id: label for label in state.labels}
            return dict(effective_at=state.effective_at, items=[dict(
                item=Item.model_validate(dict(row, sku=labels[row["id"]].sku,
                                              name_fa=labels[row["id"]].name_fa)).model_dump(),
                label=labels[row["id"]].model_dump()) for row in page],
                next_cursor=page[-1]["id"] if len(rows) > limit else None, evidence_verification="not_rechecked")

    def current_item(self, actor: UUID, business: UUID, item: UUID,
                     effective_at: datetime | None = None) -> dict:
        with self.service.database.transaction(actor, business) as c:
            original = self._item(c, business, item)
            moment = self._instant(c, effective_at)
            label = select_item_labels(c, business, [item], moment).labels[0]
            packs = c.execute(_definition_sql("pack") +
                "WHERE p.business_id=%s AND p.item_id=%s AND (p.baseline OR d.approved) "
                "AND (d.effective_at IS NULL OR d.effective_at<=%s) "
                "AND (s.effective_at IS NULL OR %s<s.effective_at) ORDER BY p.id LIMIT 2",
                (business, item, moment, moment)).fetchall()
            if len(packs) > 1:
                raise Conflict("تعریف بسته در زمان انتخاب یکتا نیست؛ بررسی لازم است")
            return dict(effective_at=moment,
                item=Item.model_validate(dict(original, sku=label.sku, name_fa=label.name_fa)).model_dump(),
                label=label.model_dump(), pack_definition=packs[0] if packs else None,
                evidence_verification="not_rechecked", **_historical_use_detail())

    def definition(self, actor: UUID, business: UUID, kind: Literal["item", "pack"], identity: UUID) -> dict:
        with self.service.database.transaction(actor, business) as c:
            row = c.execute(_definition_sql(kind) + "WHERE p.business_id=%s AND p.id=%s",
                            (business, identity)).fetchone()
            if row is None:
                raise NotFound("نسخهٔ کاتالوگ در این بیزینس موجود نیست")
            return dict(row, **_historical_use_detail()) if kind == "pack" else row

    def _history(self, actor: UUID, business: UUID, item: UUID, kind: Literal["item", "pack"],
                 after: UUID | None, limit: int) -> list[dict]:
        if not 1 <= limit <= 100:
            raise ValueError("اندازهٔ صفحه نامعتبر است")
        with self.service.database.transaction(actor, business) as c:
            self._item(c, business, item)
            rows = c.execute(_definition_sql(kind) + "WHERE p.business_id=%s AND p.item_id=%s "
                             "AND (%s::uuid IS NULL OR p.id>%s) ORDER BY p.id LIMIT %s",
                             (business, item, after, after, limit)).fetchall()
            return [dict(row, **_historical_use_detail()) for row in rows] if kind == "pack" else rows

    def propose_item(self, actor: UUID, business: UUID, key: str, value: ItemProposal) -> UUID:
        def store(c):
            self.service._inventory_evidence(c, business, value.evidence.document_id)
            fields = value.model_dump()
            fields.update(fields.pop("evidence"))
            insert(c, "item_definitions", dict(business_id=business, created_by=actor, **fields))
            return value.id

        return self.service._write(actor, business, key, "item.proposed",
                                   value.model_dump(mode="json"), store)

    def decide_item(self, actor: UUID, business: UUID, key: str,
                    identity: UUID, value: ItemDecision) -> UUID:
        def store(c):
            row = c.execute("SELECT document_id FROM herman.item_definitions "
                            "WHERE business_id=%s AND id=%s", (business, identity)).fetchone()
            if row is None:
                raise NotFound("نسخهٔ کالا موجود نیست")
            if value.approved:
                if row["document_id"] is None:
                    raise ValueError("تعریف اولیه نیاز به تصمیم جدید ندارد")
                self.service._inventory_evidence(c, business, row["document_id"])
            insert(c, "item_decisions", dict(business_id=business, definition_id=identity,
                                             actor_id=actor, **value.model_dump()))
            return identity

        return self.service._write(actor, business, key, "item.reviewed",
            dict(id=str(identity), **value.model_dump(mode="json")), store, reviewer=True)

    def item_history(self, actor: UUID, business: UUID, item: UUID,
                     after: UUID | None = None, limit: int = 50) -> list[dict]:
        return self._history(actor, business, item, "item", after, limit)

    def propose_pack(self, actor: UUID, business: UUID, key: str, value: PackProposal) -> UUID:
        def store(c):
            self.service._inventory_evidence(c, business, value.evidence.document_id)
            fields = value.model_dump()
            fields.update(fields.pop("evidence"))
            insert(c, "pack_definitions", dict(business_id=business, created_by=actor, **fields))
            return value.id

        return self.service._write(actor, business, key, "pack.proposed",
                                   value.model_dump(mode="json"), store)

    def decide_pack(self, actor: UUID, business: UUID, key: str,
                    identity: UUID, value: PackDecision) -> UUID:
        def store(c):
            row = c.execute("SELECT document_id FROM herman.pack_definitions "
                            "WHERE business_id=%s AND id=%s", (business, identity)).fetchone()
            if row is None:
                raise NotFound("نسخهٔ تبدیل موجود نیست")
            if value.approved:
                self.service._inventory_evidence(c, business, row["document_id"])
            insert(c, "pack_decisions", dict(business_id=business, definition_id=identity,
                                             actor_id=actor, **value.model_dump()))
            return identity

        return self.service._write(actor, business, key, "pack.reviewed",
            dict(id=str(identity), **value.model_dump(mode="json")), store, reviewer=True)

    def pack_history(self, actor: UUID, business: UUID, item: UUID,
                     after: UUID | None = None, limit: int = 50) -> list[dict]:
        return self._history(actor, business, item, "pack", after, limit)
