from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal, localcontext
from functools import partial
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BeforeValidator, Field, model_validator

from src.models import Model, Money, decimal_precision

Quantity = Annotated[
    Money, Field(ge=0, max_digits=24, decimal_places=6),
    BeforeValidator(partial(decimal_precision, digits=24, places=6)),
]
PositiveQuantity = Annotated[
    Money, Field(gt=0, max_digits=24, decimal_places=6),
    BeforeValidator(partial(decimal_precision, digits=24, places=6)),
]
Unit = Literal["g", "kg", "ml", "l", "each", "pack"]


class Scope(Model):
    business_id: UUID
    warehouse_id: UUID
    start: AwareDatetime
    end: AwareDatetime

    @model_validator(mode="after")
    def ordered(self) -> Scope:
        if self.end <= self.start:
            raise ValueError("پایان دوره باید بعد از شروع باشد")
        return self


class EvidenceRef(Model):
    document_id: UUID
    locator: str = Field(min_length=1, max_length=500)


class Entity(Model):
    id: UUID
    business_id: UUID


class Item(Entity):
    sku: str = Field(min_length=1, max_length=100)
    name_fa: str = Field(min_length=1, max_length=200)
    base_unit: Literal["g", "ml", "each"]
    consumption_mode: Literal["direct", "recipe"] = "direct"


class UnitConversion(Entity):
    item_id: UUID
    unit: Literal["pack"] = "pack"
    base_quantity: PositiveQuantity
    evidence: EvidenceRef


class ReviewedRecord(Entity):
    evidence: EvidenceRef
    status: Literal["proposed", "approved"] = "proposed"


class Count(ReviewedRecord):
    warehouse_id: UUID
    item_id: UUID
    occurred_at: AwareDatetime
    quantity: Quantity
    unit: Unit


class Movement(Count):
    kind: Literal["purchase", "transfer_in", "transfer_out", "supplier_return", "customer_return",
                  "waste", "other_use", "count_adjustment", "service_usage"]


class RecipeLine(Model):
    item_id: UUID
    quantity: PositiveQuantity
    unit: Unit
    basis: Literal["raw", "net"] = "raw"
    preparation_yield: Annotated[Money, Field(gt=0, le=1, max_digits=9, decimal_places=6)] = Decimal(1)

    @model_validator(mode="after")
    def consistent_yield(self) -> RecipeLine:
        if self.basis == "raw" and self.preparation_yield != 1:
            raise ValueError("مقدار خام نباید دوباره با بازده تعدیل شود")
        return self


class Recipe(ReviewedRecord):
    product_id: UUID
    valid_from: AwareDatetime
    valid_to: AwareDatetime | None = None
    output_quantity: PositiveQuantity
    output_unit: Unit
    lines: tuple[RecipeLine, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def ordered(self) -> Recipe:
        if self.valid_to is not None and self.valid_to <= self.valid_from:
            raise ValueError("بازه اعتبار رسپی نامعتبر است")
        if len({line.item_id for line in self.lines}) != len(self.lines):
            raise ValueError("ماده تکراری در یک نسخه رسپی")
        return self


class Fulfillment(ReviewedRecord):
    warehouse_id: UUID
    product_id: UUID
    occurred_at: AwareDatetime
    quantity: Quantity
    unit: Unit
    kind: Literal["sale", "complimentary", "staff", "production"] = "sale"
    fulfilled: bool = True


class Coverage(Model):
    movements_complete: bool = False
    fulfillment_complete: bool = False
    recipes_complete: bool = False
    evidence: EvidenceRef


class VariancePolicy(Model):
    absolute_base_quantity: Quantity
    relative_fraction: Annotated[Money, Field(ge=0, le=1)]
    evidence: EvidenceRef


class InventoryRequest(Model):
    scope: Scope
    target_item_id: UUID
    basis: Literal["service", "production"] = "service"
    items: tuple[Item, ...] = Field(min_length=1)
    conversions: tuple[UnitConversion, ...] = ()
    opening: Count | None = None
    closing: Count | None = None
    movements: tuple[Movement, ...] = ()
    recipes: tuple[Recipe, ...] = ()
    fulfillments: tuple[Fulfillment, ...] = ()
    coverage: Coverage
    policy: VariancePolicy

    @model_validator(mode="after")
    def same_scope(self) -> InventoryRequest:
        collections = (self.items, self.conversions, self.movements, self.recipes, self.fulfillments)
        records = [row for group in collections for row in group]
        records += [row for row in (self.opening, self.closing) if row is not None]
        if any(row.business_id != self.scope.business_id for row in records):
            raise ValueError("داده متعلق به بیزینس دیگری است")
        for group in collections:
            if len({row.id for row in group}) != len(group):
                raise ValueError("شناسه رکورد تکراری است")
        warehouse_records = [*self.movements, *self.fulfillments]
        warehouse_records += [row for row in (self.opening, self.closing) if row is not None]
        if any(row.warehouse_id != self.scope.warehouse_id for row in warehouse_records):
            raise ValueError("داده متعلق به انبار دیگری است")
        if any(not self.scope.start <= row.occurred_at < self.scope.end
               for row in (*self.movements, *self.fulfillments)):
            raise ValueError("رویداد خارج از دوره تحلیل است")
        if self.opening and (self.opening.occurred_at != self.scope.start or
                             self.opening.item_id != self.target_item_id):
            raise ValueError("شمارش ابتدا با قلم یا شروع دوره همخوانی ندارد")
        if self.closing and (self.closing.occurred_at != self.scope.end or
                             self.closing.item_id != self.target_item_id):
            raise ValueError("شمارش پایان با قلم یا پایان دوره همخوانی ندارد")
        if len({(r.item_id, r.unit) for r in self.conversions}) != len(self.conversions):
            raise ValueError("تبدیل واحد تکراری است")
        return self


class Contribution(Model):
    fulfillment_id: UUID
    recipe_ids: tuple[UUID, ...]
    quantity_base: Money
    evidence: tuple[EvidenceRef, ...]


class InventoryResult(Model):
    metric_version: str = "inventory.unexplained_variance.v1"
    scope: Scope
    target_item_id: UUID
    status: Literal["complete", "incomplete"]
    missing_fa: tuple[str, ...] = ()
    base_unit: str | None = None
    expected_usage: Money | None = None
    expected_closing: Money | None = None
    counted_closing: Money | None = None
    unexplained_shortage: Money | None = None
    variance_fraction: Money | None = None
    materiality_threshold: Money | None = None
    needs_review: bool | None = None
    contributions: tuple[Contribution, ...] = ()
    evidence: tuple[EvidenceRef, ...] = ()
    explanation_fa: str


class IncompleteData(ValueError):
    """Missing or conflicting evidence, distinct from a malformed request."""


def reconcile_inventory(request: InventoryRequest) -> InventoryResult:
    """Pure deterministic tool: no disk/network writes, no model-generated arithmetic."""
    with localcontext() as context:
        context.prec = 50
        return _reconcile(request)


def _reconcile(request: InventoryRequest) -> InventoryResult:
    items = {item.id: item for item in request.items}
    missing: list[str] = []
    if request.target_item_id not in items:
        missing.append("کالای هدف در کاتالوگ نیست")
    elif items[request.target_item_id].consumption_mode != "direct":
        missing.append("تطبیق این نسخه برای مواد پایه یا کالای فروش مستقیم است؛ محصول میانی نیاز به دفتر تولید دارد")
    for label, complete in (("گردش‌های انبار", request.coverage.movements_complete),
                            ("رویدادهای سرو یا تولید", request.coverage.fulfillment_complete),
                            ("رسپی‌ها", request.coverage.recipes_complete)):
        if not complete:
            missing.append("کامل‌بودن " + label + " تأیید نشده است")
    if request.opening is None:
        missing.append("شمارش اول دوره موجود نیست")
    if request.closing is None:
        missing.append("شمارش پایان دوره موجود نیست")
    records = [*request.movements, *request.recipes, *request.fulfillments]
    records += [row for row in (request.opening, request.closing) if row is not None]
    if any(row.status != "approved" for row in records):
        missing.append("رکورد تأییدنشده در ورودی وجود دارد")
    if any(row.kind in ("count_adjustment", "service_usage") for row in request.movements):
        missing.append("تعدیل شمارش یا مصرف سرو نباید دوباره در گردش مبنای مقایسه منظور شود")
    if any((row.kind == "production") != (request.basis == "production")
           for row in request.fulfillments if row.fulfilled):
        missing.append("سرو و تولید در یک مبنای مصرف مخلوط شده‌اند")
    evidence: list[EvidenceRef] = [request.coverage.evidence, request.policy.evidence]
    evidence.extend(row.evidence for row in records)
    evidence.extend(row.evidence for row in request.conversions)
    if missing:
        return InventoryResult(scope=request.scope, target_item_id=request.target_item_id,
            status="incomplete", missing_fa=tuple(missing), evidence=tuple(evidence),
            explanation_fa="اطلاعات کافی نیست؛ کسری یا مازاد قابل نتیجه‌گیری نیست")

    def convert(item_id: UUID, quantity: Decimal, unit: str) -> Decimal:
        if item_id not in items:
            raise IncompleteData("کالای مورد استفاده در کاتالوگ تعریف نشده است")
        base = items[item_id].base_unit
        if unit == base:
            return quantity
        if (unit, base) in (("kg", "g"), ("l", "ml")):
            return quantity * 1000
        matches = [c for c in request.conversions if c.item_id == item_id and c.unit == unit]
        if len(matches) == 1:
            return quantity * matches[0].base_quantity
        raise IncompleteData("تبدیل واحد معتبر برای کالا موجود نیست")

    recipes: dict[UUID, list[Recipe]] = defaultdict(list)
    for recipe in request.recipes:
        recipes[recipe.product_id].append(recipe)
    for versions in recipes.values():
        ordered = sorted(versions, key=lambda r: r.valid_from)
        if any(left.valid_to is None or left.valid_to > right.valid_from
               for left, right in zip(ordered, ordered[1:])):
            missing.append("بازه نسخه‌های رسپی همپوشانی دارد")

    expansion_steps = 0

    def expand(item_id: UUID, quantity: Decimal, when: datetime,
               path: tuple[UUID, ...] = ()) -> tuple[Decimal, tuple[UUID, ...]]:
        nonlocal expansion_steps
        expansion_steps += 1
        if len(path) > 32 or expansion_steps > 10000:
            raise IncompleteData("رسپی از حد پیچیدگی این نسخه بیشتر است")
        if item_id in path:
            raise IncompleteData("چرخه در رسپی تودرتو وجود دارد")
        item = items.get(item_id)
        if item is None:
            raise IncompleteData("ماده رسپی در کاتالوگ تعریف نشده است")
        if item.consumption_mode == "direct":
            return (quantity if item_id == request.target_item_id else Decimal(0)), ()
        matches = [recipe for recipe in recipes[item_id] if recipe.valid_from <= when and
                   (recipe.valid_to is None or when < recipe.valid_to)]
        if len(matches) != 1:
            raise IncompleteData("نسخه معتبر رسپی در زمان رویداد موجود یا یکتا نیست")
        recipe = matches[0]
        output = convert(item_id, recipe.output_quantity, recipe.output_unit)
        total, used = Decimal(0), [recipe.id]
        for line in recipe.lines:
            base_quantity = convert(line.item_id, line.quantity, line.unit)
            if line.basis == "net":
                base_quantity /= line.preparation_yield
            amount, nested = expand(line.item_id, quantity / output * base_quantity, when, (*path, item_id))
            total += amount
            used.extend(nested)
        return total, tuple(dict.fromkeys(used))

    contributions: list[Contribution] = []
    try:
        for row in request.fulfillments:
            if not row.fulfilled:
                continue
            quantity = convert(row.product_id, row.quantity, row.unit)
            used, recipe_ids = expand(row.product_id, quantity, row.occurred_at)
            refs = [row.evidence, *(r.evidence for r in request.recipes if r.id in recipe_ids)]
            contributions.append(Contribution(fulfillment_id=row.id, recipe_ids=recipe_ids,
                                               quantity_base=used, evidence=tuple(refs)))
        assert request.opening is not None and request.closing is not None
        opening = convert(request.target_item_id, request.opening.quantity, request.opening.unit)
        closing = convert(request.target_item_id, request.closing.quantity, request.closing.unit)
        movement_total = Decimal(0)
        for movement in request.movements:
            value = convert(movement.item_id, movement.quantity, movement.unit)
            if movement.item_id == request.target_item_id:
                sign = 1 if movement.kind in ("purchase", "transfer_in", "customer_return") else -1
                movement_total += sign * value
    except IncompleteData as exc:
        missing.append(str(exc))
    if missing:
        return InventoryResult(scope=request.scope, target_item_id=request.target_item_id,
            status="incomplete", missing_fa=tuple(missing), evidence=tuple(evidence),
            explanation_fa="اطلاعات ناقص یا متعارض است؛ نتیجه قطعی گزارش نمی‌شود")
    usage = sum((row.quantity_base for row in contributions), Decimal(0))
    expected = opening + movement_total - usage
    shortage = expected - closing
    threshold = max(request.policy.absolute_base_quantity, usage * request.policy.relative_fraction)
    return InventoryResult(scope=request.scope, target_item_id=request.target_item_id,
        status="complete", base_unit=items[request.target_item_id].base_unit,
        expected_usage=usage, expected_closing=expected, counted_closing=closing,
        unexplained_shortage=shortage, variance_fraction=shortage / usage if usage else None,
        materiality_threshold=threshold, needs_review=abs(shortage) > threshold,
        contributions=tuple(contributions), evidence=tuple(evidence),
        explanation_fa="عدد مثبت کسری و عدد منفی مازاد توضیح‌داده‌نشده است؛ علت یا تقلب از این عدد اثبات نمی‌شود")
