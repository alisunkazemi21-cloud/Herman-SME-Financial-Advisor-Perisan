"""Internal capture/review workflow for immutable historical pack interpretations."""

from uuid import UUID

from pydantic import Field, model_validator

from src.backend.inventory import EvidenceRef
from src.backend.service import NotFound, Service, insert
from src.models import Model


class BindingCheckInput(Model):
    id: UUID
    record_id: UUID
    ingredient_id: UUID | None = None
    fulfillment_id: UUID | None = None
    recipe_path: tuple[UUID, ...] = Field(default=(), max_length=33)


class BindingReviewInput(Model):
    id: UUID
    approved: bool
    definition_id: UUID | None = None
    reason_fa: str = Field(min_length=1, max_length=2000)
    evidence: EvidenceRef

    @model_validator(mode="after")
    def decision_definition(self) -> "BindingReviewInput":
        if self.approved != (self.definition_id is not None):
            raise ValueError("فقط تصمیم تأیید باید نسخهٔ تبدیل مشخص داشته باشد")
        if not self.reason_fa.strip():
            raise ValueError("دلیل بررسی لازم است")
        return self


class PackBindings:
    def __init__(self, service: Service):
        self.service = service

    def capture(self, actor: UUID, business: UUID, key: str, value: BindingCheckInput) -> UUID:
        def store(c):
            previous = c.execute(
                "SELECT id FROM herman.pack_binding_checks WHERE business_id=%s AND record_id=%s "
                "AND ingredient_id IS NOT DISTINCT FROM %s::uuid "
                "AND fulfillment_id IS NOT DISTINCT FROM %s::uuid AND recipe_path=%s::uuid[]",
                (business, value.record_id, value.ingredient_id, value.fulfillment_id, list(value.recipe_path)),
            ).fetchone()
            if previous:
                return previous["id"]
            fields = value.model_dump()
            fields["recipe_path"] = list(value.recipe_path)
            insert(c, "pack_binding_checks", dict(business_id=business, **fields))
            return value.id

        return self.service._write(actor, business, key, "pack_binding.captured",
                                   value.model_dump(mode="json"), store)

    def resolve(self, actor: UUID, business: UUID, key: str, check: UUID,
                value: BindingReviewInput) -> UUID:
        def store(c):
            row = c.execute("SELECT * FROM herman.pack_binding_checks WHERE business_id=%s AND id=%s",
                            (business, check)).fetchone()
            if row is None:
                raise NotFound("بررسی تبدیل تاریخی موجود نیست")
            if value.approved:
                self.service._inventory_evidence(c, business, value.evidence.document_id)
                definition = c.execute("SELECT document_id FROM herman.pack_definitions "
                                       "WHERE business_id=%s AND id=%s", (business, value.definition_id)).fetchone()
                if definition is None:
                    raise NotFound("نسخهٔ تبدیل در این بیزینس موجود نیست")
                source_ids = {row["record_id"], *row["recipe_path"]}
                if row["fulfillment_id"] is not None:
                    source_ids.add(row["fulfillment_id"])
                sources = c.execute("SELECT DISTINCT document_id FROM herman.records "
                                    "WHERE business_id=%s AND id=ANY(%s::uuid[])",
                                    (business, list(source_ids))).fetchall()
                documents = {definition["document_id"], *(source["document_id"] for source in sources)}
                for document in documents:
                    self.service._inventory_evidence(c, business, document)
            fields = value.model_dump()
            fields.update(fields.pop("evidence"))
            insert(c, "pack_binding_reviews", dict(business_id=business, check_id=check, actor_id=actor, **fields))
            return value.id

        return self.service._write(actor, business, key, "pack_binding.reviewed",
            dict(check_id=str(check), **value.model_dump(mode="json")), store, reviewer=True)

    def read(self, actor: UUID, business: UUID, check: UUID) -> dict:
        with self.service.database.transaction(actor, business) as c:
            row = c.execute("SELECT * FROM herman.pack_binding_checks WHERE business_id=%s AND id=%s",
                            (business, check)).fetchone()
            if row is None:
                raise NotFound("بررسی تبدیل تاریخی موجود نیست")
            resolution = c.execute("SELECT * FROM herman.pack_binding_reviews "
                                   "WHERE business_id=%s AND check_id=%s AND approved", (business, check)).fetchone()
            return dict(check=row, resolution=resolution,
                        effective_state="bound" if row["state"] == "bound" or resolution else "unresolved")

    def page(self, actor: UUID, business: UUID, after: UUID | None = None, limit: int = 20,
             record: UUID | None = None) -> dict:
        if not 1 <= limit <= 50:
            raise ValueError("اندازهٔ صفحه نامعتبر است")
        with self.service.database.transaction(actor, business) as c:
            rows = c.execute(
                "SELECT c.*,r.id AS resolution_id,r.definition_id AS reviewed_definition_id "
                "FROM herman.pack_binding_checks c LEFT JOIN herman.pack_binding_reviews r "
                "ON (r.business_id,r.check_id)=(c.business_id,c.id) AND r.approved "
                "WHERE c.business_id=%s AND (%s::uuid IS NULL OR c.id>%s) "
                "AND (%s::uuid IS NULL OR c.record_id=%s) ORDER BY c.id LIMIT %s",
                (business, after, after, record, record, limit+1),
            ).fetchall()
            return dict(checks=rows[:limit], next_cursor=rows[limit-1]["id"] if len(rows) > limit else None)

    def reviews(self, actor: UUID, business: UUID, check: UUID,
                after: UUID | None = None, limit: int = 20) -> dict:
        if not 1 <= limit <= 50:
            raise ValueError("اندازهٔ صفحه نامعتبر است")
        with self.service.database.transaction(actor, business) as c:
            rows = c.execute("SELECT * FROM herman.pack_binding_reviews "
                             "WHERE business_id=%s AND check_id=%s AND (%s::uuid IS NULL OR id>%s) "
                             "ORDER BY id LIMIT %s", (business, check, after, after, limit+1)).fetchall()
            return dict(reviews=rows[:limit], next_cursor=rows[limit-1]["id"] if len(rows) > limit else None)
