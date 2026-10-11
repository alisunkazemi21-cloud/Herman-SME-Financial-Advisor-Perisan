"""Conservative duplicate candidates; equal quantities alone never imply a duplicate event."""
from __future__ import annotations

from decimal import Decimal, localcontext
from uuid import UUID

from psycopg import sql

from src.backend.inventory_history import LIVE_RECORD, ancestors


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
        table, item_column = mapping[source["kind"]]
        row = c.execute(sql.SQL("SELECT * FROM herman.{} WHERE business_id=%s AND id=%s").format(
            sql.Identifier(table)), (business, identity)).fetchone()
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
            candidates = c.execute(sql.SQL("SELECT t.*,a.approved FROM herman.{} t "
                "JOIN herman.records r ON (r.business_id,r.id)=(t.business_id,t.id) LEFT JOIN herman.approvals a "
                "ON (a.business_id,a.record_id)=(t.business_id,t.id) WHERE t.business_id=%s AND t.id<>%s "
                "AND (a.approved IS NULL OR a.approved) AND " + LIVE_RECORD + "AND " + conditions +
                " AND NOT (r.id=ANY(%s::uuid[])) "
                "AND (r.supersedes IS NULL OR NOT (r.supersedes=ANY(%s::uuid[]))) ORDER BY t.id").format(
                    sql.Identifier(table)), [*params, predecessor_ids, predecessor_ids]).fetchall()
            conversion = c.execute("SELECT x.base_quantity,i.base_unit FROM herman.unit_conversions x "
                "JOIN herman.items i ON (i.business_id,i.id)=(x.business_id,x.item_id) "
                "WHERE x.business_id=%s AND x.item_id=%s AND x.unit='pack'", (business, row[item_column])).fetchone()

            def normalized(record):
                quantity, unit = record["quantity"], record["unit"]
                if unit in ("kg", "l"):
                    return quantity * Decimal(1000), {"kg": "g", "l": "ml"}[unit]
                if unit == "pack" and conversion:
                    return quantity * conversion["base_quantity"], conversion["base_unit"]
                return quantity, unit

            with localcontext() as context:
                context.prec = 60
                target = normalized(row)
                for candidate in candidates:
                    if normalized(candidate) == target:
                        matches.append(dict(id=candidate["id"], approved=candidate["approved"],
                            quantity=str(candidate["quantity"]), unit=candidate["unit"],
                            occurred_at=candidate["occurred_at"], reason="same_item_warehouse_event_time_quantity"))
                        if len(matches) == 100:
                            break
    return dict(found=True, documents=documents, records=matches, requires_resolution=bool(documents or matches),
                explanation_fa="موارد زیر نامزد تکرارند؛ برابری مقدار به‌تنهایی دلیل تکراری بودن نیست")
