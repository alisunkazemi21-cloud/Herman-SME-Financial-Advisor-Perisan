"""Trusted pack selection, independent of the application service."""
from uuid import UUID

from src.backend.dated_inventory import PackDefinition
from src.backend.inventory import EvidenceRef


def pack_timeline(c, business: UUID, item: UUID) -> tuple[PackDefinition, ...]:
    """Build intervals from immutable approved successors within the caller's snapshot."""
    rows = c.execute(
        "SELECT p.*,d.decided_at,d.effective_at,s.effective_at AS valid_to "
        "FROM herman.pack_definitions p LEFT JOIN herman.pack_decisions d "
        "ON (d.business_id,d.definition_id)=(p.business_id,p.id) "
        "LEFT JOIN herman.pack_decisions s ON s.business_id=p.business_id "
        "AND s.predecessor_id=p.id AND s.approved "
        "WHERE p.business_id=%s AND p.item_id=%s AND (p.baseline OR d.approved) "
        "ORDER BY d.effective_at NULLS FIRST,p.id LIMIT 10001", (business, item)).fetchall()
    if len(rows) > 10000:
        raise ValueError("تعداد نسخه‌ها از حد بررسی بیشتر است")
    return tuple(PackDefinition(
        id=row["id"], business_id=business, item_id=item, base_quantity=row["base_quantity"],
        evidence=EvidenceRef(document_id=row["document_id"], locator=row["locator"]),
        decision="baseline" if row["baseline"] else "approved", approved_at=row["decided_at"],
        valid_from=row["effective_at"], valid_to=row["valid_to"]) for row in rows)
