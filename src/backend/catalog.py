"""Internal reviewed catalog storage; routes await complete analysis integration."""

from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from src.backend.dated_inventory import PackDefinition
from src.backend.inventory import EvidenceRef, PositiveQuantity
from src.backend.service import NotFound, Service, insert
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


class Catalog:
    def __init__(self, service: Service):
        self.service = service

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
        if not 1 <= limit <= 100:
            raise ValueError("اندازهٔ صفحه نامعتبر است")
        with self.service.database.transaction(actor, business) as c:
            return c.execute(
                "SELECT p.*,d.approved,d.actor_id AS reviewed_by,d.reason_fa,d.decided_at,d.effective_at "
                "FROM herman.pack_definitions p LEFT JOIN herman.pack_decisions d "
                "ON (d.business_id,d.definition_id)=(p.business_id,p.id) "
                "WHERE p.business_id=%s AND p.item_id=%s AND (%s::uuid IS NULL OR p.id>%s) "
                "ORDER BY p.id LIMIT %s", (business, item, after, after, limit)).fetchall()


def pack_timeline(c, business: UUID, item: UUID) -> tuple[PackDefinition, ...]:
    """Build intervals from immutable approved successors within the caller's snapshot."""
    rows = c.execute(
        "SELECT p.*,d.decided_at,d.effective_at,s.effective_at AS valid_to "
        "FROM herman.pack_definitions p LEFT JOIN herman.pack_decisions d "
        "ON (d.business_id,d.definition_id)=(p.business_id,p.id) "
        "LEFT JOIN herman.pack_decisions s ON s.business_id=p.business_id "
        "AND s.predecessor_id=p.id AND s.approved "
        "WHERE p.business_id=%s AND p.item_id=%s AND (p.baseline OR d.approved) "
        "ORDER BY d.effective_at NULLS FIRST,p.id LIMIT 10001", (business, item)).fetchall()
    if len(rows) > 10000:
        raise ValueError("تعداد نسخه‌ها از حد بررسی بیشتر است")
    return tuple(PackDefinition(
        id=row["id"], business_id=business, item_id=item, base_quantity=row["base_quantity"],
        evidence=EvidenceRef(document_id=row["document_id"], locator=row["locator"]),
        decision="baseline" if row["baseline"] else "approved", approved_at=row["decided_at"],
        valid_from=row["effective_at"], valid_to=row["valid_to"]) for row in rows)
