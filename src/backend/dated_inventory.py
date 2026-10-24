"""Event-time pack calculation; persistence must supply trusted reviewed definitions."""

from collections import defaultdict
from datetime import datetime
from decimal import Decimal, localcontext
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from src.backend.inventory import (
    EvidenceRef,
    IncompleteData,
    InventoryRequest,
    InventoryResult,
    PositiveQuantity,
    UnitConversion,
    _reconcile,
)
from src.models import Model, Money


class PackDefinition(UnitConversion):
    valid_from: AwareDatetime | None = None
    valid_to: AwareDatetime | None = None
    decision: Literal["baseline", "approved", "proposed", "rejected"]
    approved_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def lifecycle(self) -> "PackDefinition":
        if self.valid_from is not None and self.valid_to is not None:
            if self.valid_to <= self.valid_from:
                raise ValueError("پایان اعتبار باید پس از شروع آن باشد")
        if self.decision == "baseline":
            if self.approved_at is not None or self.valid_from is not None:
                raise ValueError("تعریف اولیه نباید تأیید یا زمان شروع ساختگی داشته باشد")
        elif self.valid_from is None:
            raise ValueError("زمان شروع اعتبار نسخه لازم است")
        if self.decision == "approved":
            if self.approved_at is None or self.valid_from < self.approved_at:
                raise ValueError("نسخهٔ تأییدشده نمی‌تواند پیش از زمان تأیید معتبر شود")
        elif self.decision != "baseline" and self.approved_at is not None:
            raise ValueError("نسخهٔ تأییدنشده نباید زمان تأیید داشته باشد")
        return self


class DatedInventoryRequest(Model):
    inventory: InventoryRequest
    definitions: tuple[PackDefinition, ...] = Field(default=(), max_length=10000)

    @model_validator(mode="after")
    def scope_and_identity(self) -> "DatedInventoryRequest":
        if self.inventory.conversions:
            raise ValueError("تبدیل ثابت و تاریخ‌دار را هم‌زمان وارد نکنید")
        if len({row.id for row in self.definitions}) != len(self.definitions):
            raise ValueError("شناسهٔ نسخهٔ تبدیل تکراری است")
        items = {row.id for row in self.inventory.items}
        if any(row.business_id != self.inventory.scope.business_id for row in self.definitions):
            raise ValueError("نسخهٔ تبدیل متعلق به کسب‌وکار دیگری است")
        if any(row.item_id not in items for row in self.definitions):
            raise ValueError("قلم نسخهٔ تبدیل در کاتالوگ موجود نیست")
        return self


class PackUse(Model):
    context_version: Literal["pack.use.v1", "pack.use.v2"] = "pack.use.v1"
    record_id: UUID
    ingredient_id: UUID | None = None
    fulfillment_id: UUID | None = None
    recipe_path: tuple[UUID, ...] = Field(default=(), max_length=33)
    item_id: UUID
    occurred_at: AwareDatetime
    definition_id: UUID
    base_quantity: PositiveQuantity
    quantity_pack: Money
    converted_quantity: Money
    evidence: EvidenceRef

    @model_validator(mode="after")
    def context_identity(self) -> "PackUse":
        if self.context_version == "pack.use.v1":
            if self.fulfillment_id is not None or self.recipe_path:
                raise ValueError("رسید قدیمی نباید زمینهٔ جدید ساختگی داشته باشد")
        elif self.recipe_path:
            if (self.fulfillment_id is None or self.recipe_path[-1] != self.record_id
                    or len(set(self.recipe_path)) != len(self.recipe_path)
                    or self.ingredient_id not in (None, self.item_id)):
                raise ValueError("مسیر رسپی با هویت مصرف همخوانی ندارد")
        elif self.ingredient_id is not None or self.fulfillment_id not in (None, self.record_id):
            raise ValueError("زمینهٔ مصرف مستقیم نامعتبر است")
        return self


class DatedInventoryResult(Model):
    contract_version: Literal["inventory.dated_pack.v1", "inventory.dated_pack.v2"] = "inventory.dated_pack.v1"
    result: InventoryResult
    pack_uses: tuple[PackUse, ...] = ()

    @model_validator(mode="after")
    def receipt_version(self) -> "DatedInventoryResult":
        version = "pack.use.v2" if self.contract_version == "inventory.dated_pack.v2" else "pack.use.v1"
        if any(row.context_version != version for row in self.pack_uses):
            raise ValueError("نسخهٔ زمینهٔ مصرف با رسید همخوانی ندارد")
        return self


def reconcile_dated_inventory(request: DatedInventoryRequest) -> DatedInventoryResult:
    """Resolve each used instant independently; never fall back to a current factor."""
    definitions: dict[UUID, list[PackDefinition]] = defaultdict(list)
    for definition in request.definitions:
        if definition.decision in {"baseline", "approved"}:
            definitions[definition.item_id].append(definition)
    uses: list[PackUse] = []

    def resolve(item_id: UUID, quantity: Decimal, when: datetime,
                record_id: UUID, ingredient_id: UUID | None,
                fulfillment_id: UUID | None, recipe_path: tuple[UUID, ...]) -> Decimal:
        matches = [row for row in definitions[item_id]
                   if (row.valid_from is None or row.valid_from <= when)
                   and (row.valid_to is None or when < row.valid_to)]
        if len(matches) != 1:
            raise IncompleteData(
                f"تبدیل بسته برای قلم {item_id} در زمان {when.isoformat()} موجود یا یکتا نیست")
        row = matches[0]
        converted = quantity * row.base_quantity
        uses.append(PackUse(context_version="pack.use.v2", record_id=record_id, ingredient_id=ingredient_id,
                            fulfillment_id=fulfillment_id, recipe_path=recipe_path,
                            item_id=item_id, occurred_at=when, definition_id=row.id,
                            base_quantity=row.base_quantity, quantity_pack=quantity,
                            converted_quantity=converted, evidence=row.evidence))
        return converted

    with localcontext() as context:
        context.prec = 50
        result = _reconcile(request.inventory, pack_resolver=resolve)
    # Failed calculations must not look like complete conversion receipts.
    if result.status != "complete":
        return DatedInventoryResult(contract_version="inventory.dated_pack.v2", result=result)
    refs = list(result.evidence)
    for use in uses:
        if use.evidence not in refs:
            refs.append(use.evidence)
    result = result.model_copy(update={"evidence": tuple(refs)})
    return DatedInventoryResult(contract_version="inventory.dated_pack.v2", result=result, pack_uses=tuple(uses))
