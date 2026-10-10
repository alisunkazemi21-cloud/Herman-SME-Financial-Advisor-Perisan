"""Source-row provenance for immutable journal traces and saved report manifests."""

from uuid import UUID

from psycopg import Connection


def journal_origins(c: Connection, business: UUID, entries: list[UUID]) -> dict:
    rows = c.execute(
        "SELECT batch_id,entry_id,line_number,sheet,source_row,source_values FROM herman.journal_import_sources "
        "WHERE business_id=%s AND entry_id=ANY(%s) ORDER BY entry_id,line_number",
        (business, entries),
    ).fetchall()
    batches = (
        c.execute(
            "SELECT b.id,b.extraction_id,b.document_id,b.source_sha256,b.mapping,b.created_by,b.created_at,e.parser_version "
            "FROM herman.journal_import_batches b JOIN herman.extractions e ON (e.business_id,e.id)=(b.business_id,b.extraction_id) "
            "WHERE b.business_id=%s AND b.id=ANY(%s) ORDER BY b.id",
            (business, list({row["batch_id"] for row in rows})),
        ).fetchall()
        if rows
        else []
    )
    return dict(batches=batches, rows=rows)
