"""Pure historical pack interpretation shared by planned database consumers.

Metadata comes from trusted server selection, never from an approval-capable model.
The interpreter performs no capture, database access, file access or clock reads.
"""

from collections import defaultdict
from datetime import datetime
from decimal import Decimal, localcontext
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from src.backend.dated_inventory import DatedInventoryRequest, PackDefinition, PackUse
from src.backend.inventory import EvidenceRef, IncompleteData, InventoryResult, Quantity, _reconcile
from src.models import Model, exact_decimal

Interpretation = Literal["known_before_event", "migration_derived", "reviewed", "deferred"]
ObservationOrigin = Literal["migration_observation", "native_capture"]
PackUsageKey = tuple[UUID, UUID | None, UUID | None, tuple[UUID, ...]]


class PackContext(Model):
    record_id: UUID
    ingredient_id: UUID | None = None
    fulfillment_id: UUID | None = None
    recipe_path: tuple[UUID, ...] = Field(default=(), max_length=33)
    item_id: UUID
    occurred_at: AwareDatetime

    @model_validator(mode="after")
    def consistent(self) -> "PackContext":
        if self.recipe_path:
            if (
                self.fulfillment_id is None
                or self.recipe_path[-1] != self.record_id
                or len(set(self.recipe_path)) != len(self.recipe_path)
                or self.ingredient_id not in (None, self.item_id)
            ):
                raise ValueError("زمینهٔ مصرف رسپی ناسازگار است")
        elif self.ingredient_id is not None or self.fulfillment_id not in (None, self.record_id):
            raise ValueError("زمینهٔ مصرف مستقیم ناسازگار است")
        return self

    @property
    def key(self) -> PackUsageKey:
        return self.record_id, self.ingredient_id, self.fulfillment_id, self.recipe_path

    @property
    def source_ids(self) -> set[UUID]:
        return {
            self.record_id,
            *self.recipe_path,
            *(() if self.fulfillment_id is None else (self.fulfillment_id,)),
        }


class PackObservation(Model):
    definition_id: UUID
    observed_at: AwareDatetime
    origin: ObservationOrigin


class HistoricalPackCheck(PackContext):
    business_id: UUID
    id: UUID
    captured_at: AwareDatetime
    created_by: UUID | None = None
    definition_id: UUID | None = None
    state: Literal["bound", "unresolved"]
    origin: Literal["known_before_event", "migration_derived", "requires_review"]
    missing_reason: (
        Literal["missing_definition", "ambiguous_definition", "baseline_not_known_before_event"] | None
    ) = None

    @model_validator(mode="after")
    def interpretation_state(self) -> "HistoricalPackCheck":
        if self.state == "bound":
            if (
                self.definition_id is None
                or self.missing_reason is not None
                or self.origin == "requires_review"
            ):
                raise ValueError("بررسی مقید باید نسخه و منشأ معتبر داشته باشد")
        elif (
            self.definition_id is not None or self.missing_reason is None or self.origin != "requires_review"
        ):
            raise ValueError("بررسی حل‌نشده نباید تبدیل قطعی داشته باشد")
        return self


class PackResolution(Model):
    business_id: UUID
    id: UUID
    check_id: UUID
    approved: Literal[True] = True
    definition_id: UUID
    actor_id: UUID
    reason_fa: str = Field(min_length=1, max_length=2000)
    evidence: EvidenceRef
    decided_at: AwareDatetime


class PackBindingState(Model):
    business_id: UUID
    as_of: AwareDatetime
    cutover_at: AwareDatetime
    legacy_record_ids: tuple[UUID, ...] = Field(default=(), max_length=10000)
    observations: tuple[PackObservation, ...] = Field(default=(), max_length=10000)
    checks: tuple[HistoricalPackCheck, ...] = Field(default=(), max_length=10000)
    resolutions: tuple[PackResolution, ...] = Field(default=(), max_length=10000)

    @model_validator(mode="after")
    def coherent_snapshot(self) -> "PackBindingState":
        identities = [
            self.legacy_record_ids,
            tuple(o.definition_id for o in self.observations),
            tuple(c.id for c in self.checks),
            tuple(c.key for c in self.checks),
            tuple(r.id for r in self.resolutions),
            tuple(r.check_id for r in self.resolutions),
        ]
        if any(len(set(values)) != len(values) for values in identities):
            raise ValueError("شناسه یا زمینهٔ تبدیل در تصویر ورودی تکراری است")
        if self.cutover_at > self.as_of:
            raise ValueError("مرز مهاجرت پس از زمان تصویر ورودی است")
        for observation in self.observations:
            if not self.cutover_at <= observation.observed_at <= self.as_of or (
                observation.origin == "migration_observation" and observation.observed_at != self.cutover_at
            ):
                raise ValueError("زمان مشاهدهٔ نسخه ناسازگار است")
        for check in self.checks:
            if (
                check.business_id != self.business_id
                or not self.cutover_at <= check.captured_at <= self.as_of
                or check.occurred_at > check.captured_at
            ):
                raise ValueError("دامنه یا زمان بررسی تبدیل ناسازگار است")
        checks = {c.id: c for c in self.checks}
        for review in self.resolutions:
            check = checks.get(review.check_id)
            if (
                review.business_id != self.business_id
                or check is None
                or check.state != "unresolved"
                or not check.captured_at <= review.decided_at <= self.as_of
            ):
                raise ValueError("تصمیم بررسی با تصویر ورودی همخوانی ندارد")
        return self


class PackChoice(Model):
    definition: PackDefinition
    interpretation: Interpretation
    observed_at: AwareDatetime
    observation_origin: ObservationOrigin
    check_id: UUID | None = None
    resolution_id: UUID | None = None
    resolution_evidence: EvidenceRef | None = None
    resolution_decided_at: AwareDatetime | None = None


class PackInterpreter:
    """Select a supported factor; an unresolved historical check never falls back."""

    def __init__(self, definitions: tuple[PackDefinition, ...], state: PackBindingState) -> None:
        if len(definitions) > 10000 or len({d.id for d in definitions}) != len(definitions):
            raise ValueError("تعداد یا هویت نسخه‌های تبدیل نامعتبر است")
        if any(
            d.business_id != state.business_id or (d.approved_at and d.approved_at > state.as_of)
            for d in definitions
        ):
            raise ValueError("دامنه یا زمان تأیید نسخهٔ تبدیل ناسازگار است")
        self.state = state
        self.definitions = {d.id: d for d in definitions}
        self.by_item: dict[UUID, list[PackDefinition]] = defaultdict(list)
        for definition in definitions:
            if definition.decision in ("baseline", "approved"):
                self.by_item[definition.item_id].append(definition)
        self.observations = {o.definition_id: o for o in state.observations}
        eligible_ids = {d.id for rows in self.by_item.values() for d in rows}
        if (
            not eligible_ids <= self.observations.keys()
            or not self.observations.keys() <= self.definitions.keys()
        ):
            raise ValueError("مشاهدهٔ نسخه‌های تبدیل کامل یا معتبر نیست")
        for definition in definitions:
            observation = self.observations.get(definition.id)
            if (
                observation
                and observation.origin == "native_capture"
                and definition.approved_at
                and observation.observed_at > definition.approved_at
            ):
                raise ValueError("مشاهدهٔ نسخه پس از تأیید آن ثبت شده است")
        self.legacy = set(state.legacy_record_ids)
        self.checks = {c.key: c for c in state.checks}
        self.reviews = {r.check_id: r for r in state.resolutions}
        for check in state.checks:
            if check.state == "bound":
                definition = self._pinned(check.definition_id, check)
                if (
                    self._past_origin(definition, check) != check.origin
                    or self.observations[definition.id].observed_at > check.captured_at
                ):
                    raise ValueError("منشأ بررسی تبدیل با شواهد زمانی همخوانی ندارد")
            review = self.reviews.get(check.id)
            if review:
                definition = self._pinned(review.definition_id, check)
                if self.observations[definition.id].observed_at > review.decided_at:
                    raise ValueError("نسخهٔ تبدیل پس از تصمیم بررسی مشاهده شده است")

    @staticmethod
    def _eligible(definition: PackDefinition, context: PackContext) -> bool:
        return (
            definition.decision in ("baseline", "approved")
            and definition.item_id == context.item_id
            and (definition.valid_from is None or definition.valid_from <= context.occurred_at)
            and (definition.valid_to is None or context.occurred_at < definition.valid_to)
        )

    def _pinned(self, identity: UUID | None, context: PackContext) -> PackDefinition:
        definition = self.definitions.get(identity)
        if definition is None or not self._eligible(definition, context):
            raise ValueError("نسخهٔ مقید برای این مصرف واجد شرایط نیست")
        return definition

    def _past_origin(self, definition: PackDefinition, context: PackContext) -> Interpretation | None:
        observation = self.observations[definition.id]
        if definition.decision == "approved" or observation.observed_at <= context.occurred_at:
            return "known_before_event"
        if (
            context.occurred_at <= self.state.cutover_at
            and context.source_ids <= self.legacy
            and observation.origin == "migration_observation"
        ):
            return "migration_derived"
        return None

    def select(self, context: PackContext) -> PackChoice:
        check = self.checks.get(context.key)
        review = None
        if check is not None:
            if check.item_id != context.item_id or check.occurred_at != context.occurred_at:
                raise IncompleteData("بررسی تاریخی با قلم یا زمان مصرف همخوانی ندارد")
            review = self.reviews.get(check.id)
            if check.state == "unresolved" and review is None:
                raise IncompleteData("تبدیل تاریخی این مصرف نیاز به بررسی و تصمیم صریح دارد")
            definition = self._pinned(review.definition_id if review else check.definition_id, context)
            origin = "reviewed" if review else check.origin
        else:
            matches = [d for d in self.by_item[context.item_id] if self._eligible(d, context)]
            if len(matches) != 1:
                raise IncompleteData("نسخهٔ تبدیل واجد شرایط برای این مصرف موجود یا یکتا نیست")
            definition = matches[0]
            origin = (
                "deferred"
                if context.occurred_at > self.state.as_of
                else self._past_origin(definition, context)
            )
            if origin is None:
                raise IncompleteData("تعریف اولیه پس از مصرف مشاهده شده است؛ بررسی تاریخی لازم است")
        observation = self.observations[definition.id]
        return PackChoice(
            definition=definition,
            interpretation=origin,
            observed_at=observation.observed_at,
            observation_origin=observation.origin,
            check_id=check.id if check else None,
            resolution_id=review.id if review else None,
            resolution_evidence=review.evidence if review else None,
            resolution_decided_at=review.decided_at if review else None,
        )

    def normalize(
        self, quantity: Decimal, unit: str, base_unit: str, context: PackContext
    ) -> tuple[Decimal, str] | None:
        """Unavailable conversions return None; callers must never compare None pairs."""
        quantity = exact_decimal(quantity)
        if quantity < 0 or base_unit not in ("g", "ml", "each"):
            raise ValueError("مقدار یا واحد پایه معتبر نیست")
        with localcontext() as arithmetic:
            arithmetic.prec = 60
            if unit == base_unit:
                return quantity, base_unit
            if (unit, base_unit) in (("kg", "g"), ("l", "ml")):
                return quantity * 1000, base_unit
            if unit == "pack":
                try:
                    return quantity * self.select(context).definition.base_quantity, base_unit
                except IncompleteData:
                    return None
        return None


class BoundInventoryRequest(DatedInventoryRequest):
    bindings: PackBindingState

    @model_validator(mode="after")
    def trusted_scope(self) -> "BoundInventoryRequest":
        if self.bindings.business_id != self.inventory.scope.business_id:
            raise ValueError("دامنهٔ تصویر تبدیل با تحلیل همخوانی ندارد")
        PackInterpreter(self.definitions, self.bindings)
        return self


class InterpretedPackUse(PackUse):
    context_version: Literal["pack.use.v3"] = "pack.use.v3"
    quantity_pack: Quantity
    interpretation: Interpretation
    observed_at: AwareDatetime
    observation_origin: ObservationOrigin
    check_id: UUID | None = None
    resolution_id: UUID | None = None
    resolution_evidence: EvidenceRef | None = None
    resolution_decided_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def review_receipt(self) -> "InterpretedPackUse":
        review_fields = (self.resolution_id, self.resolution_evidence, self.resolution_decided_at)
        if self.interpretation == "reviewed":
            if self.check_id is None or any(field is None for field in review_fields):
                raise ValueError("رسید تبدیل بررسی‌شده باید تصمیم و شاهد داشته باشد")
            if self.resolution_decided_at < self.occurred_at or self.observed_at > self.resolution_decided_at:
                raise ValueError("زمان تصمیم و مشاهده با رسید تبدیل همخوانی ندارد")
        elif any(field is not None for field in review_fields):
            raise ValueError("رسید بدون تصمیم نباید زمینهٔ تأیید ساختگی داشته باشد")
        if self.interpretation == "deferred" and self.check_id is not None:
            raise ValueError("مصرف آینده نباید مقید شده باشد")
        if self.interpretation == "migration_derived" and (
            self.observation_origin != "migration_observation" or self.observed_at <= self.occurred_at
        ):
            raise ValueError("منشأ مهاجرتی رسید تبدیل معتبر نیست")
        with localcontext() as arithmetic:
            arithmetic.prec = 50
            if self.converted_quantity != self.quantity_pack * self.base_quantity:
                raise ValueError("مقدار تبدیل‌شده با عامل و مقدار بسته همخوانی ندارد")
        return self


class BoundInventoryResult(Model):
    contract_version: Literal["inventory.bound_pack.v1"] = "inventory.bound_pack.v1"
    result: InventoryResult
    pack_uses: tuple[InterpretedPackUse, ...] = ()
    encountered_contexts: tuple[PackContext, ...] = Field(default=(), max_length=10000)

    @model_validator(mode="after")
    def no_partial_receipt(self) -> "BoundInventoryResult":
        if self.result.status != "complete" and self.pack_uses:
            raise ValueError("نتیجهٔ ناقص نباید رسید تبدیل کامل داشته باشد")
        references = set(self.result.evidence)
        if any(
            ref not in references
            for use in self.pack_uses
            for ref in (use.evidence, use.resolution_evidence)
            if ref is not None
        ):
            raise ValueError("شاهد رسید تبدیل باید در نتیجهٔ تحلیل موجود باشد")
        return self


def reconcile_bound_inventory(request: BoundInventoryRequest) -> BoundInventoryResult:
    interpreter = PackInterpreter(request.definitions, request.bindings)
    uses: list[InterpretedPackUse] = []
    encountered: list[PackContext] = []

    def resolve(
        item_id: UUID,
        quantity: Decimal,
        when: datetime,
        record_id: UUID,
        ingredient_id: UUID | None,
        fulfillment_id: UUID | None,
        recipe_path: tuple[UUID, ...],
    ) -> Decimal:
        context = PackContext(
            record_id=record_id,
            ingredient_id=ingredient_id,
            fulfillment_id=fulfillment_id,
            recipe_path=recipe_path,
            item_id=item_id,
            occurred_at=when,
        )
        if len(encountered) >= 10000:
            raise IncompleteData("تعداد مصرف‌های بسته از حد بررسی این نسخه بیشتر است")
        encountered.append(context)
        choice = interpreter.select(context)
        converted = quantity * choice.definition.base_quantity
        metadata = choice.model_dump(exclude={"definition"})
        uses.append(
            InterpretedPackUse(
                **context.model_dump(),
                **metadata,
                definition_id=choice.definition.id,
                base_quantity=choice.definition.base_quantity,
                quantity_pack=quantity,
                converted_quantity=converted,
                evidence=choice.definition.evidence,
            )
        )
        return converted

    with localcontext() as arithmetic:
        arithmetic.prec = 50
        result = _reconcile(request.inventory, pack_resolver=resolve)
    if result.status != "complete":
        return BoundInventoryResult(result=result, encountered_contexts=tuple(encountered))
    evidence = list(result.evidence)
    for use in uses:
        for reference in (use.evidence, use.resolution_evidence):
            if reference is not None and reference not in evidence:
                evidence.append(reference)
    return BoundInventoryResult(
        result=result.model_copy(update={"evidence": tuple(evidence)}),
        pack_uses=tuple(uses),
        encountered_contexts=tuple(encountered),
    )
