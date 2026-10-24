"""Dated catalog selection; original item identities and receipts remain intact."""

from datetime import datetime
from uuid import UUID


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
