"""Conservative duplicate candidates; equal quantities alone never imply a duplicate event."""
from __future__ import annotations

import json
from uuid import UUID

from psycopg import sql

from src.backend.inventory_history import LIVE_RECORD, ancestors
from src.backend.pack_binding_selection import SelectionLimit, select_binding_state
from src.backend.pack_interpretation import PackContext, PackInterpreter
from src.backend.pack_selection import pack_timeline

MAX_DUPLICATE_ROWS = 10000
MAX_DUPLICATE_BYTES = 8 * 1024 * 1024


def document_matches(c, business: UUID, document_id: UUID, excluded: tuple[UUID, ...] = ()) -> list[dict]:
    return c.execute("SELECT other.id,other.original_name,other.created_at FROM herman.documents original "
        "JOIN herman.documents other ON other.business_id=original.business_id AND other.sha256=original.sha256 "
        "AND other.id<>original.id WHERE original.business_id=%s AND original.id=%s "
        "AND NOT (other.id=ANY(%s::uuid[])) ORDER BY other.created_at,other.id LIMIT 100",
        (business, document_id, list(excluded))).fetchall()


def record_matches(c, business: UUID, identity: UUID) -> dict:
    source = c.execute("SELECT kind,document_id,supersedes FROM herman.records WHERE business_id=%s AND id=%s",
                       (business, identity)).fetchone()
    if source is None:
        return dict(found=False, documents=[], records=[], requires_resolution=False)
    lineage = ancestors(c, business, identity) if source["supersedes"] else []
    predecessor_ids = [row["id"] for row in lineage if row["id"] != identity]
    documents = document_matches(c, business, source["document_id"],
                                 tuple(row["document_id"] for row in lineage))
    mapping = {"count": ("stock_counts", "item_id"), "movement": ("stock_movements", "item_id"),
               "fulfillment": ("fulfillments", "product_id")}
    matches = []
    if source["kind"] in mapping:
        remaining, encoded_bytes = MAX_DUPLICATE_ROWS, 0

        def charge(rows):
            nonlocal remaining, encoded_bytes
            remaining -= len(rows)
            encoded_bytes += len(json.dumps(rows, ensure_ascii=False, default=str,
                                            sort_keys=True, separators=(",", ":")).encode())
            if remaining < 0 or encoded_bytes > MAX_DUPLICATE_BYTES:
                raise SelectionLimit("حجم بررسی موارد مشابه بیش از حد این نسخه است؛ پیش از تأیید، سوابق را بررسی کنید")
            return rows

        def read(query, parameters):
            query += sql.SQL(" LIMIT %s") if isinstance(query, sql.Composable) else " LIMIT %s"
            return charge(c.execute(query, (*parameters, remaining + 1)).fetchall())

        table, item_column = mapping[source["kind"]]
        target_rows = read(sql.SQL("SELECT * FROM herman.{} WHERE business_id=%s AND id=%s").format(
            sql.Identifier(table)), (business, identity))
        row = target_rows[0] if target_rows else None
        if row:
            conditions = "t.warehouse_id=%s AND t." + item_column + "=%s AND t.occurred_at=%s"
            params = [business, identity, row["warehouse_id"], row[item_column], row["occurred_at"]]
            if source["kind"] != "count":
                conditions += " AND t.kind=%s"
                params.append(row["kind"])
            if source["kind"] == "fulfillment":
                conditions += " AND t.fulfilled=%s"
                params.append(row["fulfilled"])
            # All candidates share item and timestamp; narrow first using the existing scoped period indexes.
            candidates = read(sql.SQL("SELECT t.*,a.approved FROM herman.{} t "
                "JOIN herman.records r ON (r.business_id,r.id)=(t.business_id,t.id) LEFT JOIN herman.approvals a "
                "ON (a.business_id,a.record_id)=(t.business_id,t.id) WHERE t.business_id=%s AND t.id<>%s "
                "AND (a.approved IS NULL OR a.approved) AND " + LIVE_RECORD + "AND " + conditions +
                " AND NOT (r.id=ANY(%s::uuid[])) "
                "AND (r.supersedes IS NULL OR NOT (r.supersedes=ANY(%s::uuid[]))) ORDER BY t.id").format(
                    sql.Identifier(table)), [*params, predecessor_ids, predecessor_ids])
            definitions = pack_timeline(c, business, row[item_column])
            charge([definition.model_dump(mode="json") for definition in definitions])
            item_rows = read("SELECT base_unit FROM herman.items WHERE business_id=%s AND id=%s",
                             (business, row[item_column]))
            item = item_rows[0] if item_rows else None
            record_ids = [identity, *(candidate["id"] for candidate in candidates)]
            bindings = select_binding_state(c, business, definitions, record_ids,
                                            record_ids if source["kind"] == "fulfillment" else (), read=read)
            snapshot = dict(target=row, candidates=candidates,
                            definitions=[definition.model_dump(mode="json") for definition in definitions],
                            pack_bindings=bindings.model_dump(mode="json"))
            if len(json.dumps(snapshot, ensure_ascii=False, default=str, sort_keys=True,
                              separators=(",", ":")).encode()) > MAX_DUPLICATE_BYTES:
                raise SelectionLimit("حجم بررسی موارد مشابه بیش از حد این نسخه است؛ پیش از تأیید، سوابق را بررسی کنید")
            interpreter = PackInterpreter(definitions, bindings)

            def normalized(record):
                context = PackContext(record_id=record["id"], item_id=row[item_column],
                    occurred_at=record["occurred_at"],
                    fulfillment_id=record["id"] if source["kind"] == "fulfillment" else None)
                return (interpreter.normalize(record["quantity"], record["unit"], item["base_unit"], context)
                        if item else None)

            target = normalized(row)
            for candidate in candidates:
                value = normalized(candidate)
                if target is not None and value is not None and value == target:
                    matches.append(dict(id=candidate["id"], approved=candidate["approved"],
                        quantity=str(candidate["quantity"]), unit=candidate["unit"],
                        occurred_at=candidate["occurred_at"], reason="same_item_warehouse_event_time_quantity"))
                    if len(matches) == 100:
                        break
    return dict(found=True, documents=documents, records=matches, requires_resolution=bool(documents or matches),
                explanation_fa="موارد زیر نامزد تکرارند؛ برابری مقدار به‌تنهایی دلیل تکراری بودن نیست")
