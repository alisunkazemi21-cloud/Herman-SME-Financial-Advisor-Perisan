"""Persisted correction lineage; the request-only inventory calculator stays unchanged."""

from __future__ import annotations

import json
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field

from src.backend.inventory import Count, Fulfillment, Movement, Recipe
from src.models import Model

MAX_CORRECTION_DEPTH = 64
MAX_LINEAGE_ROWS = 10000
MAX_LINEAGE_BYTES = 8 * 1024 * 1024
LIVE_RECORD = (
    "NOT EXISTS (SELECT 1 FROM herman.approvals successor WHERE successor.business_id=r.business_id "
    "AND successor.supersedes=r.id AND successor.approved) "
)
RECORD_STATE = (
    "CASE WHEN a.record_id IS NULL THEN 'pending' WHEN NOT a.approved THEN 'rejected' "
    "WHEN successor.record_id IS NOT NULL THEN 'superseded' ELSE 'approved' END"
)
RecordState = Literal["pending", "approved", "rejected", "superseded"]
RecordKind = Literal["count", "movement", "recipe", "fulfillment"]


class CountCorrection(Model):
    record_kind: Literal["count"]
    replacement: Count


class MovementCorrection(Model):
    record_kind: Literal["movement"]
    replacement: Movement


class RecipeCorrection(Model):
    record_kind: Literal["recipe"]
    replacement: Recipe


class FulfillmentCorrection(Model):
    record_kind: Literal["fulfillment"]
    replacement: Fulfillment


CorrectionInput = Annotated[
    CountCorrection | MovementCorrection | RecipeCorrection | FulfillmentCorrection,
    Field(discriminator="record_kind"),
]

CHAIN = (
    "WITH RECURSIVE chain AS ("
    "SELECT id AS selected_record_id,id,supersedes,0 AS depth FROM herman.records "
    "WHERE business_id=%s AND id=ANY(%s::uuid[]) AND (NOT %s OR supersedes IS NOT NULL) "
    "UNION ALL SELECT chain.selected_record_id,r.id,r.supersedes,chain.depth+1 "
    "FROM herman.records r JOIN chain ON r.id=chain.supersedes "
    "WHERE r.business_id=%s AND chain.depth<%s) "
)


def ancestors(c, business: UUID, identity: UUID) -> list[dict]:
    rows = c.execute(
        CHAIN + "SELECT chain.*,r.document_id FROM chain JOIN herman.records r "
        "ON r.business_id=%s AND r.id=chain.id ORDER BY chain.depth",
        (business, [identity], False, business, MAX_CORRECTION_DEPTH, business),
    ).fetchall()
    if rows and rows[-1]["supersedes"] is not None:
        raise ValueError("زنجیره اصلاح بیش از حد مجاز است")
    return rows


def current_successor(c, business: UUID, identity: UUID) -> UUID | None:
    row = c.execute(
        "WITH RECURSIVE revisions AS (SELECT record_id,0 AS depth FROM herman.approvals "
        "WHERE business_id=%s AND supersedes=%s AND approved "
        "UNION ALL SELECT a.record_id,revisions.depth+1 FROM revisions JOIN herman.approvals a "
        "ON a.business_id=%s AND a.supersedes=revisions.record_id AND a.approved WHERE revisions.depth<%s) "
        "SELECT * FROM revisions ORDER BY depth DESC LIMIT 1",
        (business, identity, business, MAX_CORRECTION_DEPTH),
    ).fetchone()
    if row and row["depth"] == MAX_CORRECTION_DEPTH:
        raise ValueError("زنجیره اصلاح بیش از حد مجاز است")
    return row["record_id"] if row else None


def correction_provenance(c, business: UUID, identities: list[UUID]) -> list[dict]:
    rows = c.execute(
        CHAIN + "SELECT chain.selected_record_id,chain.depth,r.id,r.kind,r.supersedes,"
        "r.document_id,r.locator,r.created_by,r.created_at,d.sha256 AS document_sha256,"
        "a.actor_id AS reviewed_by,a.created_at AS reviewed_at,a.reason_fa,"
        "CASE WHEN s.id IS NULL THEN NULL ELSE to_jsonb(s) || jsonb_build_object("
        "'mapping',b.mapping,'source_sha256',e.source_sha256,'parser_version',e.parser_version) END AS import_origin "
        "FROM chain JOIN herman.records r ON r.business_id=%s AND r.id=chain.id "
        "JOIN herman.documents d ON (d.business_id,d.id)=(r.business_id,r.document_id) "
        "JOIN herman.approvals a ON (a.business_id,a.record_id)=(r.business_id,r.id) AND a.approved "
        "LEFT JOIN herman.record_sources s ON (s.business_id,s.id)=(r.business_id,r.id) "
        "LEFT JOIN herman.import_batches b ON (b.business_id,b.id)=(s.business_id,s.batch_id) "
        "LEFT JOIN herman.extractions e ON (e.business_id,e.id)=(s.business_id,s.extraction_id) "
        "ORDER BY chain.selected_record_id,chain.depth LIMIT %s",
        (business, identities, True, business, MAX_CORRECTION_DEPTH, business, MAX_LINEAGE_ROWS + 1),
    ).fetchall()
    if len(rows) > MAX_LINEAGE_ROWS or any(
        row["depth"] == MAX_CORRECTION_DEPTH and row["supersedes"] is not None for row in rows
    ):
        raise ValueError("سوابق اصلاح بیش از حد مجاز است؛ دامنه تحلیل را کوچک‌تر کنید")
    encoded = json.dumps(rows, default=str, ensure_ascii=False)
    if len(encoded.encode("utf-8")) > MAX_LINEAGE_BYTES:
        raise ValueError("حجم شواهد اصلاح بیش از حد مجاز است؛ دامنه تحلیل را کوچک‌تر کنید")
    return json.loads(encoded)
