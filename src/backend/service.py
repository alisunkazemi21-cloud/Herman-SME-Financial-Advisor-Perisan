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
from src.backend.dated_inventory import PackDefinition
from src.backend.duplicates import document_matches, record_matches
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
)
from src.backend.inventory_history import (
    LIVE_RECORD,
    MAX_CORRECTION_DEPTH,
    RECORD_STATE,
    RecordKind,
    RecordState,
    ancestors,
    correction_provenance,
    current_successor,
)
from src.backend.inventory_selection import SelectionLimit, select_inputs
from src.backend.item_selection import ItemLabelState
from src.backend.pack_binding_selection import capture_past_contexts
from src.backend.pack_interpretation import BoundInventoryRequest, PackBindingState, reconcile_bound_inventory
from src.models import Model

MAX_ANALYSIS_ROWS = 10000
MAX_ANALYSIS_BYTES = 8 * 1024 * 1024


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
            rows = c.execute(sql.SQL("SELECT " + fields + " FROM herman.{} WHERE business_id=%s "
                "AND (%s::uuid IS NULL OR id>%s) ORDER BY id LIMIT %s").format(sql.Identifier(resource)),
                (business, after, after, limit)).fetchall()
            for row in rows:
                row.pop("created_xid", None)
            return rows

    def record(self, actor: UUID, business: UUID, identity: UUID) -> dict:
        with self.database.transaction(actor, business) as c:
            source = c.execute("SELECT * FROM herman.records WHERE business_id=%s AND id=%s",
                               (business, identity)).fetchone()
            if source is None:
                raise NotFound("رکورد موجود نیست")
            source.pop("created_xid", None)
            table = {"count": "stock_counts", "movement": "stock_movements", "recipe": "recipes",
                     "fulfillment": "fulfillments"}[source["kind"]]
            detail = c.execute(sql.SQL("SELECT * FROM herman.{} WHERE business_id=%s AND id=%s").format(
                sql.Identifier(table)), (business, identity)).fetchone()
            if table == "recipes":
                detail["lines"] = c.execute("SELECT * FROM herman.recipe_lines WHERE business_id=%s AND recipe_id=%s",
                                             (business, identity)).fetchall()
            decision = c.execute("SELECT * FROM herman.approvals WHERE business_id=%s AND record_id=%s",
                                 (business, identity)).fetchone()
            origin = c.execute("SELECT s.*,b.mapping,e.parser_version,e.source_sha256 FROM herman.record_sources s "
                "JOIN herman.import_batches b ON (b.business_id,b.id)=(s.business_id,s.batch_id) "
                "JOIN herman.extractions e ON (e.business_id,e.id)=(s.business_id,s.extraction_id) "
                "WHERE s.business_id=%s AND s.id=%s", (business, identity)).fetchone()
            successor = c.execute("SELECT record_id FROM herman.approvals "
                "WHERE business_id=%s AND supersedes=%s AND approved", (business, identity)).fetchone()
            state = "pending" if decision is None else "rejected" if not decision["approved"] else (
                "superseded" if successor else "approved")
            return dict(source=source, detail=detail, decision=decision, origin=origin, state=state,
                        superseded_by=successor["record_id"] if successor else None,
                        correction_scope="whole_record" if source["supersedes"] else None,
                        correction_lineage=ancestors(c, business, identity) if source["supersedes"] else [],
                        duplicate_candidates=record_matches(c, business, identity))

    def inventory_records(self, actor: UUID, business: UUID, after: UUID | None = None, limit: int = 20,
                          state: RecordState | None = None, kind: RecordKind | None = None,
                          supersedes: UUID | None = None) -> dict:
        if not 1 <= limit <= 50 or state not in (None, "pending", "approved", "rejected", "superseded"):
            raise ValueError("اندازه صفحه یا وضعیت رکورد نامعتبر است")
        if kind not in (None, "count", "movement", "recipe", "fulfillment"):
            raise ValueError("نوع رکورد نامعتبر است")
        with self.database.transaction(actor, business) as c:
            rows = c.execute(
                "SELECT r.id,r.kind,r.document_id,r.locator,r.created_at,r.supersedes,"
                "successor.record_id AS superseded_by," + RECORD_STATE + " AS state FROM herman.records r "
                "LEFT JOIN herman.approvals a ON (a.business_id,a.record_id)=(r.business_id,r.id) "
                "LEFT JOIN herman.approvals successor ON successor.business_id=r.business_id "
                "AND successor.supersedes=r.id AND successor.approved "
                "WHERE r.business_id=%s AND (%s::uuid IS NULL OR r.id>%s) "
                "AND (%s::text IS NULL OR r.kind=%s) AND (%s::uuid IS NULL OR r.supersedes=%s) "
                "AND (%s::text IS NULL OR " + RECORD_STATE + "=%s) ORDER BY r.id LIMIT %s",
                (business, after, after, kind, kind, supersedes, supersedes, state, state, limit + 1),
            ).fetchall()
            return dict(records=rows[:limit], next_cursor=rows[limit - 1]["id"] if len(rows) > limit else None)

    def document_duplicates(self, actor: UUID, business: UUID, identity: UUID) -> dict:
        with self.database.transaction(actor, business) as c:
            if not c.execute("SELECT 1 FROM herman.documents WHERE business_id=%s AND id=%s",
                             (business, identity)).fetchone():
                raise NotFound("سند موجود نیست")
            return dict(documents=document_matches(c, business, identity), reason="identical_file_sha256")

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
        # aborted serialization/deadlock transactions, never an unrelated domain uniqueness error.
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
            except (psycopg.errors.SerializationFailure, psycopg.errors.DeadlockDetected):
                if attempt == 2:
                    raise Conflict("تعارض هم‌زمان رخ داد؛ درخواست را دوباره تلاش کنید") from None
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
                    # Keep staging names short enough for Windows paths; the published name is still the full hash.
                    temporary = folder / (uuid4().hex + ".tmp")
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
        kind = "movement" if isinstance(value, Movement) else (
            "count" if isinstance(value, Count) else "recipe" if isinstance(value, Recipe) else "fulfillment")
        return self._write(actor, business, key, kind + ".proposed", value.model_dump(mode="json"),
                           lambda c: self._insert_proposal(c, actor, business, value))

    def _insert_proposal(self, c, actor, business, value, supersedes: UUID | None = None) -> UUID:
        if value.business_id != business or value.status != "proposed":
            raise ValueError("پیشنهاد با دامنه بیزینس همخوانی ندارد")
        kind, table = ("movement", "stock_movements") if isinstance(value, Movement) else (
            ("count", "stock_counts") if isinstance(value, Count) else (
                ("recipe", "recipes") if isinstance(value, Recipe) else ("fulfillment", "fulfillments")))

        fields = value.model_dump()
        fields.pop("status")
        evidence = fields.pop("evidence")
        insert(c, "records", dict(business_id=business, id=value.id, kind=kind, created_by=actor,
                                  supersedes=supersedes, **evidence))
        lines = fields.pop("lines", None)
        insert(c, table, fields)
        for line in lines or ():
            insert(c, "recipe_lines", dict(business_id=business, recipe_id=value.id, **line))
        return value.id

    @staticmethod
    def _inventory_predecessor(c, business: UUID, identity: UUID, kind: str) -> None:
        row = c.execute("SELECT r.kind,a.approved," + LIVE_RECORD + "AS is_current FROM herman.records r "
            "LEFT JOIN herman.approvals a ON (a.business_id,a.record_id)=(r.business_id,r.id) "
            "WHERE r.business_id=%s AND r.id=%s", (business, identity)).fetchone()
        if row is None:
            raise NotFound("رکورد پیشین در این بیزینس موجود نیست")
        if row["kind"] != kind or not row["approved"] or not row["is_current"]:
            raise Conflict("اصلاح باید به رکورد تأییدشده و جایگزین‌نشده از همان نوع ارجاع دهد")

    def _inventory_evidence(self, c, business: UUID, document: UUID) -> None:
        row = c.execute("SELECT sha256 FROM herman.documents WHERE business_id=%s AND id=%s",
                        (business, document)).fetchone()
        if row is None:
            raise NotFound("شاهد اصلاح در این بیزینس موجود نیست")
        try:
            content = (self.blob_root / str(business) / row["sha256"]).read_bytes()
        except OSError as exc:
            raise Conflict("فایل شاهد اصلاح در دسترس نیست") from exc
        if hashlib.sha256(content).hexdigest() != row["sha256"]:
            raise Conflict("فایل شاهد اصلاح تغییر کرده است")

    def correct_inventory(self, actor: UUID, business: UUID, key: str, predecessor: UUID,
                          value: Count | Movement | Recipe | Fulfillment) -> UUID:
        kind = "movement" if isinstance(value, Movement) else (
            "count" if isinstance(value, Count) else "recipe" if isinstance(value, Recipe) else "fulfillment")

        def store(c):
            self._inventory_predecessor(c, business, predecessor, kind)
            if len(ancestors(c, business, predecessor)) > MAX_CORRECTION_DEPTH:
                raise ValueError("زنجیره اصلاح بیش از حد مجاز است")
            self._inventory_evidence(c, business, value.evidence.document_id)
            return self._insert_proposal(c, actor, business, value, predecessor)

        return self._write(actor, business, key, "record.correction_proposed",
            dict(predecessor=str(predecessor), record_kind=kind, replacement=value.model_dump(mode="json")), store)

    def approve(self, actor: UUID, business: UUID, key: str, record_id: UUID, approved: bool, reason: str,
                duplicate_resolution: str | None = None) -> UUID:
        if not 1 <= len(reason.strip()) <= 2000:
            raise ValueError("دلیل بررسی لازم است")
        if duplicate_resolution not in (None, "same_event", "distinct_event"):
            raise ValueError("تصمیم تکرار نامعتبر است")
        if approved and duplicate_resolution == "same_event":
            raise ValueError("رکورد تکراری همان رویداد نباید تأیید شود")

        def store(c):
            record = c.execute("SELECT kind,document_id,supersedes FROM herman.records "
                               "WHERE business_id=%s AND id=%s", (business, record_id)).fetchone()
            if record is None:
                raise NotFound("رکورد موجود نیست")
            if approved and record["supersedes"] is not None:
                self._inventory_predecessor(c, business, record["supersedes"], record["kind"])
                self._inventory_evidence(c, business, record["document_id"])
            duplicates = record_matches(c, business, record_id)
            if not duplicates["found"]:
                raise NotFound("رکورد موجود نیست")
            if duplicates["requires_resolution"] and approved and duplicate_resolution != "distinct_event":
                raise Conflict("نامزد تکرار وجود دارد؛ برای تأیید، مستقل بودن رویداد را با دلیل تأیید کنید")
            insert(c, "approvals", dict(business_id=business, record_id=record_id, approved=approved,
                                        actor_id=actor, reason_fa=reason, duplicate_resolution=duplicate_resolution))
            return record_id

        payload = dict(record_id=str(record_id), approved=approved, reason=reason)
        if duplicate_resolution is not None:
            payload["duplicate_resolution"] = duplicate_resolution
        return self._write(actor, business, key, "record.reviewed", payload, store, reviewer=True)

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
            def select():
                try:
                    return select_inputs(c, business, value.scope, value.opening_id, value.closing_id,
                                         max_rows=MAX_ANALYSIS_ROWS)
                except SelectionLimit:
                    raise ValueError("حجم ورودی تحلیل بیش از حد بررسی است؛ بازهٔ کوچک‌تری انتخاب کنید") from None

            selected = select()
            for role, identity in (("opening", value.opening_id), ("closing", value.closing_id)):
                if identity is not None and selected[role] is None:
                    successor = current_successor(c, business, identity)
                    if successor:
                        raise Conflict("شمارش جایگزین شده است؛ نسخه فعلی را صریح انتخاب کنید: " +
                                       str(successor))
                    pending = c.execute("SELECT supersedes FROM herman.records WHERE business_id=%s AND id=%s",
                                        (business, identity)).fetchone()
                    if pending and pending["supersedes"]:
                        raise Conflict("اصلاح شمارش برای استفاده در تحلیل تأیید نشده است")
                    raise NotFound("شمارش موجود نیست یا رد شده است")
            def prepare(inputs):
                definitions = tuple(PackDefinition.model_validate(row) for row in inputs.pop("pack_definitions"))
                bindings = PackBindingState.model_validate(inputs.pop("pack_bindings"))
                labels = ItemLabelState.model_validate(inputs.pop("item_labels"))
                request = InventoryRequest(scope=value.scope, target_item_id=value.target_item_id, basis=value.basis,
                    **inputs, coverage=value.coverage, policy=value.policy)
                labels.validate_selection(request.items, business, request.scope.end)
                snapshot = request.model_dump(mode="json")
                snapshot["pack_definitions"] = [row.model_dump(mode="json") for row in definitions]
                snapshot["pack_bindings"] = bindings.model_dump(mode="json")
                snapshot["item_labels"] = labels.model_dump(mode="json")
                if len(canonical(snapshot).encode()) > MAX_ANALYSIS_BYTES:
                    raise ValueError("حجم ورودی تحلیل بیش از حد بررسی است؛ بازهٔ کوچک‌تری انتخاب کنید")
                bound = BoundInventoryRequest(inventory=request.model_copy(update={"conversions": ()}),
                                              definitions=definitions, bindings=bindings)
                return request, bound, snapshot

            request, bound, _ = prepare(selected)
            preflight = reconcile_bound_inventory(bound)
            capture_past_contexts(c, business, preflight.encountered_contexts, bound.bindings.as_of)
            request, bound, snapshot = prepare(select())
            calculated = reconcile_bound_inventory(bound)
            captured = {check.key for check in bound.bindings.checks}
            if any(context.occurred_at <= bound.bindings.as_of and context.key not in captured
                   for context in calculated.encountered_contexts):
                raise Conflict("زمان رویداد هنگام بررسی گذشته است؛ تحلیل را دوباره درخواست کنید")
            definitions = bound.definitions
            refs = [request.coverage.evidence, request.policy.evidence, *(row.evidence for row in definitions)]
            labels = ItemLabelState.model_validate(snapshot["item_labels"])
            refs.extend(label.evidence for label in labels.labels if label.evidence is not None)
            refs.extend(resolution.evidence for resolution in bound.bindings.resolutions)
            refs.extend(row.evidence for row in (*request.movements, *request.recipes,
                *request.fulfillments, *request.conversions))
            refs.extend(row.evidence for row in (request.opening, request.closing) if row is not None)
            for document_id in {ref.document_id for ref in refs}:
                source = c.execute("SELECT sha256 FROM herman.documents WHERE business_id=%s AND id=%s",
                                   (business, document_id)).fetchone()
                if source is None:
                    raise NotFound("شاهد تحلیل در این بیزینس موجود نیست")
                try:
                    content = (self.blob_root / str(business) / source["sha256"]).read_bytes()
                except OSError as exc:
                    raise Conflict("فایل شاهد موجود نیست؛ تحلیل ثبت نشد") from exc
                if hashlib.sha256(content).hexdigest() != source["sha256"]:
                    raise Conflict("فایل شاهد تغییر کرده است؛ تحلیل ثبت نشد")
            result = calculated.result.model_dump(mode="json")
            record_ids = [row.id for row in (*request.movements, *request.recipes, *request.fulfillments)]
            record_ids.extend(row.id for row in (request.opening, request.closing) if row is not None)
            provenance = c.execute("SELECT s.*,b.mapping,e.source_sha256,e.parser_version FROM herman.record_sources s "
                "JOIN herman.import_batches b ON (b.business_id,b.id)=(s.business_id,s.batch_id) "
                "JOIN herman.extractions e ON (e.business_id,e.id)=(s.business_id,s.extraction_id) "
                "WHERE s.business_id=%s AND s.id=ANY(%s::uuid[]) ORDER BY s.id", (business, record_ids)).fetchall()
            # Convert UUIDs to JSON strings without altering numeric calculator inputs.
            provenance_json = json.loads(json.dumps(provenance, default=str, ensure_ascii=False))
            corrections = correction_provenance(c, business, record_ids)
            identity = uuid4()
            insert(c, "analysis_runs", dict(business_id=business, id=identity, actor_id=actor,
                input_sha256=hashlib.sha256(canonical(snapshot).encode()).hexdigest(),
                input_snapshot=Jsonb(snapshot), result=Jsonb(result), source_provenance=Jsonb(provenance_json),
                correction_provenance=Jsonb(corrections),
                pack_uses=Jsonb([row.model_dump(mode="json") for row in calculated.pack_uses])))
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

    def analysis_view(self, actor: UUID, business: UUID, identity: UUID) -> dict:
        """Historical receipt plus a separate live comparison in the same tenant snapshot."""
        from src.backend.inventory_freshness import freshness

        with self.database.transaction(actor, business) as c:
            row = c.execute("SELECT * FROM herman.analysis_runs WHERE business_id=%s AND id=%s",
                            (business, identity)).fetchone()
            if row is None:
                raise NotFound("تحلیل موجود نیست")
            return dict(**row, freshness=freshness(c, business, row))
