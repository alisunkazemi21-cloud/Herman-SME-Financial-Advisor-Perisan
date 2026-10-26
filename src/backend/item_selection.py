"""Dated catalog selection; original item identities and receipts remain intact."""

from collections.abc import Callable, Iterable
from datetime import datetime
from typing import Literal
from uuid import UUID

from psycopg import Connection
from pydantic import AwareDatetime, Field, model_validator

from src.backend.inventory import EvidenceRef, Item
from src.backend.pack_binding_selection import SelectionLimit
from src.models import Model

MAX_LABEL_ROWS = 10000


class ItemLabel(Model):
    definition_id: UUID
    business_id: UUID
    item_id: UUID
    sku: str = Field(min_length=1, max_length=100)
    name_fa: str = Field(min_length=1, max_length=200)
    decision: Literal["baseline", "approved"]
    approved_at: AwareDatetime | None = None
    valid_from: AwareDatetime | None = None
    valid_to: AwareDatetime | None = None
    evidence: EvidenceRef | None = None

    @model_validator(mode="after")
    def lifecycle(self) -> "ItemLabel":
        if self.valid_from is not None and self.valid_to is not None and self.valid_to <= self.valid_from:
            raise ValueError("پایان اعتبار باید پس از شروع آن باشد")
        if self.decision == "baseline":
            if self.approved_at is not None or self.valid_from is not None or self.evidence is not None:
                raise ValueError("نام اولیه نباید تأیید، شاهد یا زمان شروع ساختگی داشته باشد")
        elif (self.evidence is None or self.approved_at is None or self.valid_from is None
              or self.approved_at > self.valid_from):
            raise ValueError("نام تأییدشده به شاهد و زمان تأیید معتبر نیاز دارد")
        return self


class ItemLabelState(Model):
    contract_version: Literal["catalog.item_labels.v1"] = "catalog.item_labels.v1"
    business_id: UUID
    effective_at: AwareDatetime
    labels: tuple[ItemLabel, ...] = Field(default=(), max_length=MAX_LABEL_ROWS)

    @model_validator(mode="after")
    def scope_and_identity(self) -> "ItemLabelState":
        if (len({row.item_id for row in self.labels}) != len(self.labels)
                or len({row.definition_id for row in self.labels}) != len(self.labels)):
            raise ValueError("شناسهٔ کالا یا نسخهٔ نام تکراری است")
        if any(row.business_id != self.business_id
               or (row.valid_from is not None and row.valid_from > self.effective_at)
               or (row.valid_to is not None and self.effective_at >= row.valid_to) for row in self.labels):
            raise ValueError("نام کالا با کسب‌وکار یا زمان انتخاب همخوانی ندارد")
        return self

    def validate_selection(self, items: Iterable[Item], business: UUID, effective_at: datetime) -> None:
        """Require exact item identities and display text at the reporting instant."""
        selected = {row.id: row for row in items}
        if (self.business_id != business or self.effective_at != effective_at
                or selected.keys() != {row.item_id for row in self.labels}
                or any(selected[row.item_id].business_id != business
                       or selected[row.item_id].sku != row.sku
                       or selected[row.item_id].name_fa != row.name_fa for row in self.labels)):
            raise ValueError("نام‌های انتخاب‌شده با ورودی تحلیل همخوانی ندارند")


def select_item_labels(c: Connection, business: UUID, item_ids: Iterable[UUID], effective_at: datetime,
                       *, read: Callable | None = None) -> ItemLabelState:
    """Read published labels with one physical metadata row per selected item."""
    identities = set()
    for position, identity in enumerate(item_ids):
        if position >= MAX_LABEL_ROWS:
            raise SelectionLimit("item label identity selection exceeds row limit")
        identities.add(identity)
    # Validate the instant even when there are no selected items.
    state = ItemLabelState(business_id=business, effective_at=effective_at)
    if not identities:
        return state
    query = (
        "SELECT p.id AS definition_id,p.business_id,p.item_id,p.sku,p.name_fa,p.baseline,"
        "d.decided_at AS approved_at,lower(a.validity) AS valid_from,upper(a.validity) AS valid_to,"
        "p.document_id,p.locator FROM herman.item_alias_periods a "
        "JOIN herman.item_definitions p ON (p.business_id,p.id)=(a.business_id,a.definition_id) "
        "LEFT JOIN herman.item_decisions d ON (d.business_id,d.definition_id)=(p.business_id,p.id) "
        "WHERE a.business_id=%s AND a.item_id=ANY(%s::uuid[]) AND a.validity @> %s::timestamptz "
        "AND (p.baseline OR d.approved) ORDER BY p.item_id,p.id")
    parameters = (business, sorted(identities), state.effective_at)
    rows = (read(query, parameters) if read is not None else
            c.execute(query + " LIMIT %s", (*parameters, MAX_LABEL_ROWS + 1)).fetchall())
    if len(rows) > MAX_LABEL_ROWS:
        raise SelectionLimit("item label metadata exceeds row limit")
    labels = []
    for source in rows:
        row = dict(source)
        baseline = row.pop("baseline")
        document, locator = row.pop("document_id"), row.pop("locator")
        labels.append(ItemLabel(**row, decision="baseline" if baseline else "approved",
                                evidence=None if baseline else dict(document_id=document, locator=locator)))
    state = ItemLabelState(business_id=business, effective_at=effective_at, labels=labels)
    if {row.item_id for row in state.labels} != identities:
        raise ValueError("نام یکتای منتشرشده برای همهٔ کالاها در زمان انتخاب موجود نیست")
    return state


def resolve_sku(connection, business: UUID, sku: str, occurred_at: datetime) -> dict:
    rows = connection.execute(
        "SELECT d.item_id,d.id AS definition_id FROM herman.item_definitions d "
        "JOIN herman.item_alias_periods a ON (a.business_id,a.definition_id)=(d.business_id,d.id) "
        "WHERE a.business_id=%s AND a.sku=%s AND a.validity @> %s::timestamptz LIMIT 2",
        (business, sku, occurred_at),
    ).fetchall()
    if len(rows) != 1:
        raise ValueError("SKU ردیف در زمان رویداد تعریف یکتا ندارد")
    return rows[0]
