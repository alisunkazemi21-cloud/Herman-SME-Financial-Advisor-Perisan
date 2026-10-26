"""Immutable internal metadata for reviewed warehouse-period completeness."""

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from src.backend.inventory import Coverage, EvidenceRef, Scope
from src.models import Model

CATEGORIES = (
    "opening_count", "closing_count", "purchases", "sales", "returns", "transfers",
    "waste", "staff_meals", "complimentary", "production", "other_use", "recipes",
)
CATEGORY_LABELS_FA = dict(zip(CATEGORIES, (
    "شمارش ابتدا", "شمارش پایان", "خرید", "فروش", "برگشت", "انتقال", "ضایعات",
    "غذای کارکنان", "پذیرایی رایگان", "تولید", "سایر مصارف", "رسپی‌ها",
)))
Basis = Literal["service", "production"]


class CoverageCategory(Model):
    status: Literal["records_complete", "no_events", "not_applicable", "missing", "incomplete"]
    evidence: EvidenceRef | None = None
    note_fa: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def positive_evidence(self) -> "CoverageCategory":
        if self.status in ("records_complete", "no_events", "not_applicable") and self.evidence is None:
            raise ValueError("ادعای کامل‌بودن به شاهد نیاز دارد")
        return self


class CoverageProposal(Model):
    id: UUID
    scope: Scope
    basis: Basis
    categories: dict[str, CoverageCategory] = Field(min_length=12, max_length=12)
    evidence: EvidenceRef
    supersedes_id: UUID | None = None

    @model_validator(mode="after")
    def category_contract(self) -> "CoverageProposal":
        if set(self.categories) != set(CATEGORIES):
            raise ValueError("هر دوازده دستهٔ پوشش باید دقیقاً یک بار ثبت شوند")
        for name, entry in self.categories.items():
            if entry.status == "not_applicable" and name != "recipes":
                raise ValueError("عدم کاربرد فقط برای رسپی مجاز است")
            if name in ("opening_count", "closing_count") and entry.status == "no_events":
                raise ValueError("شمارش ابتدا و پایان نمی‌تواند بدون رویداد باشد")
        if self.supersedes_id == self.id:
            raise ValueError("ارزیابی نمی‌تواند جایگزین خودش باشد")
        return self


class CoverageDecision(Model):
    approved: bool
    reason_fa: str = Field(min_length=1, max_length=2000)


class CategoryStats(Model):
    event_count: int = Field(ge=0, le=10000)
    approved_count: int = Field(ge=0, le=10000)
    pending_count: int = Field(ge=0, le=10000)

    @model_validator(mode="after")
    def partition(self) -> "CategoryStats":
        if self.event_count != self.approved_count + self.pending_count:
            raise ValueError("آمار وضعیت رکوردها همخوانی ندارد")
        return self


class CoverageDataset(Model):
    available: bool
    signature: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    row_count: int = Field(ge=0, le=10001)
    stats: dict[str, CategoryStats] = Field(max_length=12)
    required_recipe_products: int = Field(default=0, ge=0, le=10000)
    unreviewed_count: int = Field(ge=0, le=10000)
    evidence_refs: tuple[EvidenceRef, ...] = Field(default=(), max_length=10000)

    @model_validator(mode="after")
    def bounded(self) -> "CoverageDataset":
        if self.available:
            if self.signature is None or self.row_count > 10000 or set(self.stats) != set(CATEGORIES):
                raise ValueError("پروندهٔ پوشش باید کامل و محدود باشد")
        elif self.signature is not None:
            raise ValueError("پروندهٔ ناموجود امضای جزئی ندارد")
        return self


class CoverageReview(Model):
    assessment_id: UUID
    actor_id: UUID
    approved: Literal[True]
    reason_fa: str = Field(min_length=1, max_length=2000)
    decided_at: AwareDatetime
    dataset: CoverageDataset


class CoverageSnapshot(Model):
    contract_version: Literal["inventory.coverage.v1"] = "inventory.coverage.v1"
    scope: Scope
    basis: Basis
    as_of: AwareDatetime
    dataset: CoverageDataset
    assessment: CoverageProposal | None = None
    decision: CoverageReview | None = None

    @model_validator(mode="after")
    def review_identity(self) -> "CoverageSnapshot":
        if (self.assessment is None) != (self.decision is None):
            raise ValueError("ارزیابی و تصمیم باید با هم انتخاب شوند")
        if self.assessment is not None:
            self.validate_scope(self.assessment.scope, self.assessment.basis)
            if self.decision.assessment_id != self.assessment.id or self.decision.decided_at > self.as_of:
                raise ValueError("شناسه یا زمان تصمیم با انتخاب همخوانی ندارد")
        return self

    def validate_scope(self, scope: Scope, basis: str) -> None:
        if self.scope != scope or self.basis != basis:
            raise ValueError("پوشش با دامنه یا مبنای تحلیل همخوانی ندارد")

    @property
    def provisional(self) -> bool:
        return self.decision is not None and self.decision.decided_at < self.scope.end

    @property
    def blockers_fa(self) -> tuple[str, ...]:
        blockers = []
        if not self.dataset.available:
            blockers.append("تعداد داده‌های پوشش بیش از حد مجاز است؛ بررسی محدودتر لازم است")
        if self.assessment is None or self.decision is None:
            return (*blockers, "ارزیابی کامل‌بودن رکوردها هنوز تأیید نشده است")
        if (not self.decision.dataset.available or not self.dataset.available
                or self.decision.dataset.signature != self.dataset.signature):
            blockers.append("داده‌ها پس از بررسی تغییر کرده‌اند؛ ارزیابی جدید لازم است")
        if self.dataset.available:
            if self.dataset.unreviewed_count:
                blockers.append("برخی رکوردهای انتخاب‌شده هنوز بررسی و تأیید نشده‌اند")
            for name in CATEGORIES:
                entry, stats = self.assessment.categories[name], self.dataset.stats[name]
                invalid = entry.status in ("missing", "incomplete") or stats.pending_count > 0
                if entry.status == "records_complete":
                    invalid |= stats.approved_count == 0
                elif entry.status == "no_events":
                    invalid |= stats.event_count > 0 or (name == "recipes" and self.dataset.required_recipe_products > 0)
                elif entry.status == "not_applicable":
                    invalid |= name != "recipes" or self.dataset.required_recipe_products > 0
                if invalid:
                    blockers.append(f"پوشش دستهٔ {CATEGORY_LABELS_FA[name]} ناقص یا با رکوردهای انتخاب‌شده ناسازگار است")
        return tuple(blockers)

    @property
    def complete(self) -> bool:
        return not self.blockers_fa

    @property
    def evidence_refs(self) -> tuple[EvidenceRef, ...]:
        refs = list(self.dataset.evidence_refs)
        if self.assessment is not None:
            refs.append(self.assessment.evidence)
            refs.extend(entry.evidence for entry in self.assessment.categories.values() if entry.evidence)
        return tuple({(ref.document_id, ref.locator): ref for ref in refs}.values())

    def derive(self, declaration: Coverage) -> Coverage:
        return declaration.model_copy(update={
            name: getattr(declaration, name) and self.complete
            for name in ("movements_complete", "fulfillment_complete", "recipes_complete")})
