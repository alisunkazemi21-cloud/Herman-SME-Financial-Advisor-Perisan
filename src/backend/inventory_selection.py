"""One database selection contract for reconciliation and freshness checks."""

from __future__ import annotations

from uuid import UUID

from psycopg import Connection, sql

from src.backend.dated_inventory import PackDefinition
from src.backend.inventory import Scope
from src.backend.inventory_history import LIVE_RECORD
from src.backend.item_selection import select_item_labels
from src.backend.pack_binding_selection import SelectionLimit as SelectionLimit
from src.backend.pack_binding_selection import select_binding_state


def select_inputs(c: Connection, business: UUID, scope: Scope, opening: UUID | None,
                  closing: UUID | None, *, max_rows: int | None = None, include_bindings: bool = True,
                  include_labels: bool = True) -> dict:
    remaining = max_rows

    def read(query, parameters):
        nonlocal remaining
        if remaining is not None:
            query += sql.SQL(" LIMIT %s") if isinstance(query, sql.Composable) else " LIMIT %s"
            parameters = (*parameters, remaining + 1)
        rows = c.execute(query, parameters).fetchall()
        if remaining is not None:
            remaining -= len(rows)
            if remaining < 0:
                raise SelectionLimit("inventory selection exceeds comparison row limit")
        return rows

    items = read("SELECT * FROM herman.items WHERE business_id=%s ORDER BY id", (business,))
    labels = None
    if include_labels:
        labels = select_item_labels(c, business, (row["id"] for row in items), scope.end,
                                    read=read if max_rows is not None else None)
        by_item = {row.item_id: row for row in labels.labels}
        items = [dict(row, sku=by_item[row["id"]].sku, name_fa=by_item[row["id"]].name_fa) for row in items]
    conversions = read("SELECT * FROM herman.unit_conversions WHERE business_id=%s ORDER BY id", (business,))
    for row in conversions:
        row["evidence"] = dict(document_id=row.pop("document_id"), locator=row.pop("locator"))

    definitions = read(
        "SELECT p.*,d.decided_at,d.effective_at,s.effective_at AS valid_to "
        "FROM herman.pack_definitions p LEFT JOIN herman.pack_decisions d "
        "ON (d.business_id,d.definition_id)=(p.business_id,p.id) "
        "LEFT JOIN herman.pack_decisions s ON s.business_id=p.business_id "
        "AND s.predecessor_id=p.id AND s.approved "
        "WHERE p.business_id=%s AND (p.baseline OR d.approved) ORDER BY p.id", (business,))
    definitions = [PackDefinition(
        id=row["id"], business_id=business, item_id=row["item_id"], base_quantity=row["base_quantity"],
        evidence=dict(document_id=row["document_id"], locator=row["locator"]),
        decision="baseline" if row["baseline"] else "approved", approved_at=row["decided_at"],
        valid_from=row["effective_at"], valid_to=row["valid_to"]).model_dump() for row in definitions]

    def records(table: str, where: str, parameters: tuple) -> list[dict]:
        rows = read(sql.SQL(
            "SELECT t.*,r.document_id,r.locator,a.approved FROM herman.{} t "
            "JOIN herman.records r ON (r.business_id,r.id)=(t.business_id,t.id) "
            "LEFT JOIN herman.approvals a ON (a.business_id,a.record_id)=(t.business_id,t.id) "
            "WHERE t.business_id=%s AND (a.approved IS NULL OR a.approved) AND " + LIVE_RECORD +
            "AND (r.supersedes IS NULL OR a.approved) AND " + where + " ORDER BY t.id"
        ).format(sql.Identifier(table)), (business, *parameters))
        for row in rows:
            row["evidence"] = dict(document_id=row.pop("document_id"), locator=row.pop("locator"))
            row["status"] = "approved" if row.pop("approved") else "proposed"
        return rows

    def count(identity: UUID | None) -> dict | None:
        rows = records("stock_counts", "t.id=%s", (identity,)) if identity else []
        return rows[0] if rows else None

    period = (scope.warehouse_id, scope.start, scope.end)
    where = "t.warehouse_id=%s AND t.occurred_at>=%s AND t.occurred_at<%s"
    movements = records("stock_movements", where, period)
    fulfillments = records("fulfillments", where, period)
    recipes = records("recipes", "t.valid_from<%s AND (t.valid_to IS NULL OR t.valid_to>%s)",
                      (scope.end, scope.start))
    by_recipe = {row["id"]: row for row in recipes}
    for row in recipes:
        row["lines"] = []
    if recipes:
        lines = read(
            "SELECT recipe_id,item_id,quantity,unit,basis,preparation_yield FROM herman.recipe_lines "
            "WHERE business_id=%s AND recipe_id=ANY(%s::uuid[]) ORDER BY recipe_id,item_id",
            (business, list(by_recipe)))
        for line in lines:
            by_recipe[line.pop("recipe_id")]["lines"].append(line)
    selected = dict(items=items, conversions=conversions, movements=movements, fulfillments=fulfillments,
                    recipes=recipes, opening=count(opening), closing=count(closing), pack_definitions=definitions)
    if labels is not None:
        selected["item_labels"] = labels.model_dump()
    if include_bindings:
        records = [*movements, *recipes, *fulfillments,
                   *(row for row in (selected["opening"], selected["closing"]) if row is not None)]
        selected["pack_bindings"] = select_binding_state(
            c, business, tuple(PackDefinition.model_validate(row) for row in definitions),
            (row["id"] for row in records), (row["id"] for row in fulfillments),
            read=read if max_rows is not None else None,
        ).model_dump()
    return selected
