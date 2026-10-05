"""Tenant-scoped application service. Only authenticated server code supplies actor_id."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Callable
from uuid import UUID, uuid4

import psycopg
from filelock import FileLock
from psycopg import sql
from psycopg.types.json import Jsonb
from pydantic import Field

from src.backend.database import Database
from src.backend.inventory import (
    Count,
    Coverage,
    Fulfillment,
    InventoryRequest,
    Item,
    Movement,
    Recipe,
    Scope,
    UnitConversion,
    VariancePolicy,
    reconcile_inventory,
)
from src.models import Model


class Conflict(ValueError):
    pass


class NotFound(LookupError):
    pass


class Warehouse(Model):
    id: UUID
    business_id: UUID
    name: str = Field(min_length=1, max_length=200)


class AnalysisInput(Model):
    scope: Scope
    target_item_id: UUID
    opening_id: UUID | None = None
    closing_id: UUID | None = None
    basis: str = Field(default="service", pattern="^(service|production)$")
    coverage: Coverage
    policy: VariancePolicy


def canonical(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def insert(connection, table: str, fields: dict) -> None:
    connection.execute(sql.SQL("INSERT INTO herman.{} ({}) VALUES ({})").format(
        sql.Identifier(table), sql.SQL(",").join(map(sql.Identifier, fields)),
        sql.SQL(",").join(sql.Placeholder() for _ in fields)), tuple(fields.values()))


class Service:
    def __init__(self, database: Database, blob_root: Path):
        self.database = database
        self.blob_root = blob_root.resolve()

    def businesses(self, actor: UUID) -> list[dict]:
        with self.database.transaction(actor) as c:
            return c.execute("SELECT * FROM herman.list_businesses()").fetchall()

    def page(self, actor: UUID, business: UUID, resource: str, after: UUID | None = None,
             limit: int = 50) -> list[dict]:
        tables = {"items", "warehouses", "documents", "records", "audit_events", "analysis_runs"}
        if resource not in tables or not 1 <= limit <= 100:
            raise ValueError("منبع یا اندازه صفحه نامعتبر است")
        with self.database.transaction(actor, business) as c:
            fields = "id,actor_id,input_sha256,created_at" if resource == "analysis_runs" else "*"
            return c.execute(sql.SQL("SELECT " + fields + " FROM herman.{} WHERE business_id=%s "
                "AND (%s::uuid IS NULL OR id>%s) ORDER BY id LIMIT %s").format(sql.Identifier(resource)),
                (business, after, after, limit)).fetchall()

    def record(self, actor: UUID, business: UUID, identity: UUID) -> dict:
        with self.database.transaction(actor, business) as c:
            source = c.execute("SELECT * FROM herman.records WHERE business_id=%s AND id=%s",
                               (business, identity)).fetchone()
            if source is None:
                raise NotFound("رکورد موجود نیست")
            table = {"count": "stock_counts", "movement": "stock_movements", "recipe": "recipes",
                     "fulfillment": "fulfillments"}[source["kind"]]
            detail = c.execute(sql.SQL("SELECT * FROM herman.{} WHERE business_id=%s AND id=%s").format(
                sql.Identifier(table)), (business, identity)).fetchone()
            if table == "recipes":
                detail["lines"] = c.execute("SELECT * FROM herman.recipe_lines WHERE business_id=%s AND recipe_id=%s",
                                             (business, identity)).fetchall()
            decision = c.execute("SELECT * FROM herman.approvals WHERE business_id=%s AND record_id=%s",
                                 (business, identity)).fetchone()
            return dict(source=source, detail=detail, decision=decision)

    def create_business(self, actor: UUID, name: str, industry: str, key: str) -> UUID:
        for attempt in range(3):
            try:
                with self.database.transaction(actor) as c:
                    business = c.execute("SELECT herman.create_business(%s,%s,%s) AS id",
                                         (name, industry, key)).fetchone()["id"]
                    c.execute("SELECT set_config('herman.business_id',%s,true)", (str(business),))
                    if not c.execute("SELECT 1 FROM herman.audit_events WHERE business_id=%s "
                                     "AND action='business.created'", (business,)).fetchone():
                        self._audit(c, actor, business, "business.created", business)
                    return business
            except (psycopg.errors.UniqueViolation, psycopg.errors.SerializationFailure):
                if attempt == 2:
                    raise
            except psycopg.errors.InvalidParameterValue as exc:
                raise Conflict("کلید درخواست با ایجاد بیزینس قبلی همخوانی ندارد") from exc
        raise RuntimeError("unreachable")

    def _audit(self, c, actor, business, action, entity):
        insert(c, "audit_events", dict(id=uuid4(), business_id=business, actor_id=actor,
                                      action=action, entity_id=entity, request_id=uuid4()))

    def _write(self, actor: UUID, business: UUID, key: str, action: str, payload: dict,
               operation: Callable, reviewer: bool = False) -> UUID:
        if not 1 <= len(key) <= 200:
            raise ValueError("idempotency key must contain 1–200 characters")
        digest = hashlib.sha256(canonical(dict(action=action, payload=payload)).encode()).hexdigest()
        # A concurrent duplicate may see an older repeatable-read snapshot. Retry only the
        # idempotency-key conflict/serialization, never an unrelated domain uniqueness error.
        for attempt in range(3):
            try:
                with self.database.transaction(actor, business, write=True, reviewer=reviewer) as c:
                    previous = c.execute("SELECT * FROM herman.idempotency_keys WHERE business_id=%s AND key=%s",
                                         (business, key)).fetchone()
                    if previous:
                        if previous["request_hash"] != digest:
                            raise Conflict("این کلید قبلاً برای درخواست متفاوت استفاده شده است")
                        return previous["result_id"]
                    entity = operation(c)
                    insert(c, "idempotency_keys", dict(business_id=business, key=key,
                                                       request_hash=digest, result_id=entity))
                    self._audit(c, actor, business, action, entity)
                    return entity
            except psycopg.errors.UniqueViolation as exc:
                with self.database.transaction(actor, business) as c:
                    previous = c.execute("SELECT * FROM herman.idempotency_keys WHERE business_id=%s AND key=%s",
                                         (business, key)).fetchone()
                if previous:
                    if previous["request_hash"] != digest:
                        raise Conflict("این کلید قبلاً برای درخواست متفاوت استفاده شده است") from exc
                    return previous["result_id"]
                raise
            except psycopg.errors.SerializationFailure:
                if attempt == 2:
                    raise
        raise RuntimeError("unreachable")

    def document(self, actor: UUID, business: UUID, key: str, name: str, media_type: str, content: bytes) -> UUID:
        if len(content) > 10 * 1024 * 1024 or not content:
            raise ValueError("سند باید بین یک بایت و ۱۰ مگابایت باشد")
        if not 1 <= len(name) <= 200 or not 1 <= len(media_type) <= 100:
            raise ValueError("نام یا نوع سند نامعتبر است")
        digest = hashlib.sha256(content).hexdigest()
        payload = dict(sha256=digest, original_name=name, media_type=media_type, byte_size=len(content))

        def store(c):
            # Path contains only validated UUID/hash. Client filenames are metadata, never paths.
            folder = self.blob_root / str(business)
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / digest
            with FileLock(str(path) + ".lock", timeout=10):
                if path.exists():
                    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                        raise Conflict("فایل شاهد با هش ثبت‌شده همخوانی ندارد")
                else:
                    temporary = folder / (digest + "." + str(uuid4()) + ".tmp")
                    with temporary.open("xb") as target:
                        target.write(content)
                        target.flush()
                        os.fsync(target.fileno())
                    os.replace(temporary, path)
            identity = uuid4()
            insert(c, "documents", dict(id=identity, business_id=business, created_by=actor, **payload))
            return identity

        return self._write(actor, business, key, "document.uploaded", payload, store)

    def read_document(self, actor: UUID, business: UUID, identity: UUID) -> tuple[dict, bytes]:
        with self.database.transaction(actor, business) as c:
            row = c.execute("SELECT * FROM herman.documents WHERE business_id=%s AND id=%s",
                            (business, identity)).fetchone()
            if row is None:
                raise NotFound("سند موجود نیست")
            content = (self.blob_root / str(business) / row["sha256"]).read_bytes()
            if hashlib.sha256(content).hexdigest() != row["sha256"]:
                raise Conflict("شاهد تغییر کرده است")
            return row, content

    def catalog(self, actor: UUID, business: UUID, key: str, value: Item | Warehouse | UnitConversion) -> UUID:
        if value.business_id != business:
            raise ValueError("دامنه بیزینس متفاوت است")
        table = "items" if isinstance(value, Item) else "warehouses" if isinstance(value, Warehouse) else "unit_conversions"

        def store(c):
            fields = value.model_dump()
            if "evidence" in fields:
                fields.update(fields.pop("evidence"))
            insert(c, table, fields)
            return value.id

        # Unit factors affect arithmetic; only a reviewer/owner can create them.
        return self._write(actor, business, key, table + ".created", value.model_dump(mode="json"), store,
                           reviewer=isinstance(value, UnitConversion))

    def propose(self, actor: UUID, business: UUID, key: str, value: Count | Movement | Recipe | Fulfillment) -> UUID:
        if value.business_id != business or value.status != "proposed":
            raise ValueError("رکورد باید متعلق به بیزینس و در وضعیت پیشنهاد باشد")
        kind, table = ("movement", "stock_movements") if isinstance(value, Movement) else (
            ("count", "stock_counts") if isinstance(value, Count) else (
                ("recipe", "recipes") if isinstance(value, Recipe) else ("fulfillment", "fulfillments")))

        def store(c):
            fields = value.model_dump()
            fields.pop("status")
            evidence = fields.pop("evidence")
            insert(c, "records", dict(business_id=business, id=value.id, kind=kind, created_by=actor, **evidence))
            lines = fields.pop("lines", None)
            insert(c, table, fields)
            for line in lines or ():
                insert(c, "recipe_lines", dict(business_id=business, recipe_id=value.id, **line))
            return value.id

        return self._write(actor, business, key, kind + ".proposed", value.model_dump(mode="json"), store)

    def approve(self, actor: UUID, business: UUID, key: str, record_id: UUID, approved: bool, reason: str) -> UUID:
        if not 1 <= len(reason.strip()) <= 2000:
            raise ValueError("دلیل بررسی لازم است")

        def store(c):
            insert(c, "approvals", dict(business_id=business, record_id=record_id, approved=approved,
                                        actor_id=actor, reason_fa=reason))
            return record_id

        return self._write(actor, business, key, "record.reviewed",
                           dict(record_id=str(record_id), approved=approved, reason=reason), store, reviewer=True)

    def analyze(self, actor: UUID, business: UUID, key: str, value: AnalysisInput) -> UUID:
        if value.scope.business_id != business:
            raise ValueError("دامنه بیزینس متفاوت است")

        def run(c):
            for ref in (value.coverage.evidence, value.policy.evidence):
                if c.execute("SELECT 1 FROM herman.documents WHERE business_id=%s AND id=%s",
                             (business, ref.document_id)).fetchone() is None:
                    raise NotFound("شاهد پوشش یا آستانه در بیزینس موجود نیست")
            if c.execute("SELECT 1 FROM herman.warehouses WHERE business_id=%s AND id=%s",
                         (business, value.scope.warehouse_id)).fetchone() is None:
                raise NotFound("انبار موجود نیست")
            items = c.execute("SELECT * FROM herman.items WHERE business_id=%s", (business,)).fetchall()
            conversions = c.execute("SELECT * FROM herman.unit_conversions WHERE business_id=%s", (business,)).fetchall()
            for row in conversions:
                row["evidence"] = dict(document_id=row.pop("document_id"), locator=row.pop("locator"))

            def records(table, where, parameters):
                rows = c.execute(sql.SQL("SELECT t.*,r.document_id,r.locator,a.approved FROM herman.{} t "
                    "JOIN herman.records r ON (r.business_id,r.id)=(t.business_id,t.id) "
                    "LEFT JOIN herman.approvals a ON (a.business_id,a.record_id)=(t.business_id,t.id) "
                    "WHERE t.business_id=%s AND (a.approved IS NULL OR a.approved) AND " + where +
                    " ORDER BY t.id").format(sql.Identifier(table)), (business, *parameters)).fetchall()
                for row in rows:
                    row["evidence"] = dict(document_id=row.pop("document_id"), locator=row.pop("locator"))
                    row["status"] = "approved" if row.pop("approved") else "proposed"
                return rows

            def count(identity):
                if identity is None:
                    return None
                rows = records("stock_counts", "t.id=%s", (identity,))
                if not rows:
                    raise NotFound("شمارش موجود نیست یا رد شده است")
                return rows[0]

            period = (value.scope.warehouse_id, value.scope.start, value.scope.end)
            where = "t.warehouse_id=%s AND t.occurred_at>=%s AND t.occurred_at<%s"
            movements = records("stock_movements", where, period)
            fulfillments = records("fulfillments", where, period)
            recipes = records("recipes", "t.valid_from<%s AND (t.valid_to IS NULL OR t.valid_to>%s)",
                              (value.scope.end, value.scope.start))
            for row in recipes:
                row["lines"] = c.execute("SELECT item_id,quantity,unit,basis,preparation_yield "
                    "FROM herman.recipe_lines WHERE business_id=%s AND recipe_id=%s ORDER BY item_id",
                    (business, row["id"])).fetchall()
            request = InventoryRequest(scope=value.scope, target_item_id=value.target_item_id, basis=value.basis,
                items=items, conversions=conversions, opening=count(value.opening_id), closing=count(value.closing_id),
                movements=movements, fulfillments=fulfillments, recipes=recipes, coverage=value.coverage, policy=value.policy)
            snapshot = request.model_dump(mode="json")
            refs = [request.coverage.evidence, request.policy.evidence]
            refs.extend(row.evidence for row in (*request.movements, *request.recipes,
                *request.fulfillments, *request.conversions))
            refs.extend(row.evidence for row in (request.opening, request.closing) if row is not None)
            for document_id in {ref.document_id for ref in refs}:
                source = c.execute("SELECT sha256 FROM herman.documents WHERE business_id=%s AND id=%s",
                                   (business, document_id)).fetchone()
                try:
                    content = (self.blob_root / str(business) / source["sha256"]).read_bytes()
                except FileNotFoundError as exc:
                    raise Conflict("فایل شاهد موجود نیست؛ تحلیل ثبت نشد") from exc
                if hashlib.sha256(content).hexdigest() != source["sha256"]:
                    raise Conflict("فایل شاهد تغییر کرده است؛ تحلیل ثبت نشد")
            result = reconcile_inventory(request).model_dump(mode="json")
            identity = uuid4()
            insert(c, "analysis_runs", dict(business_id=business, id=identity, actor_id=actor,
                input_sha256=hashlib.sha256(canonical(snapshot).encode()).hexdigest(),
                input_snapshot=Jsonb(snapshot), result=Jsonb(result)))
            return identity

        # Completeness and materiality assertions are reviewed inputs, not model guesses.
        return self._write(actor, business, key, "inventory.analyzed", value.model_dump(mode="json"), run, reviewer=True)

    def analysis(self, actor: UUID, business: UUID, identity: UUID) -> dict:
        with self.database.transaction(actor, business) as c:
            row = c.execute("SELECT * FROM herman.analysis_runs WHERE business_id=%s AND id=%s",
                            (business, identity)).fetchone()
            if row is None:
                raise NotFound("تحلیل موجود نیست")
            return row
