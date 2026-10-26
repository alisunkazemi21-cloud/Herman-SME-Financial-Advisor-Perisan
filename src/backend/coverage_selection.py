"""Bounded read-only selection of an approved completeness head and live dossier."""

from collections.abc import Callable
from uuid import UUID

from src.backend.coverage_budget import coverage_budget
from src.backend.coverage_models import (
    CoverageDataset,
    CoverageProposal,
    CoverageReview,
    CoverageSnapshot,
)
from src.backend.inventory import Scope
from src.backend.pack_binding_selection import SelectionLimit


def proposal_from_row(row: dict) -> CoverageProposal:
    return CoverageProposal(id=row["id"], scope=Scope(
        business_id=row["business_id"], warehouse_id=row["warehouse_id"],
        start=row["period_start"], end=row["period_end"]), basis=row["basis"],
        categories=row["categories"], evidence=dict(document_id=row["document_id"], locator=row["locator"]),
        supersedes_id=row["supersedes_id"])


def select_coverage(c, business: UUID, scope: Scope, basis: str,
                    read: Callable | None = None) -> CoverageSnapshot:
    if scope.business_id != business or basis not in ("service", "production"):
        raise ValueError("دامنه یا مبنای پوشش نامعتبر است")
    remaining = 10000

    def bounded(query, parameters):
        nonlocal remaining
        if read is not None:
            return read(query, parameters)
        rows = c.execute(query + " LIMIT %s", (*parameters, remaining + 1)).fetchall()
        remaining -= len(rows)
        if remaining < 0:
            raise SelectionLimit("coverage metadata selection exceeds row limit")
        return rows

    with coverage_budget(c):
        dossier = bounded("SELECT herman.coverage_dossier(%s,%s,%s,%s,%s) AS dataset",
                          (business, scope.warehouse_id, scope.start, scope.end, basis))[0]["dataset"]
    dataset = CoverageDataset.model_validate(dossier)
    # The dossier is aggregated in PostgreSQL; charge its physical facts to the
    # caller's shared selection budget instead of counting it as a single row.
    if dataset.available and dataset.row_count:
        bounded("SELECT 1 AS coverage_fact FROM generate_series(1,%s)", (dataset.row_count,))
    rows = bounded(
        "SELECT p.*,d.actor_id,d.approved,d.reason_fa,d.decided_at,d.dataset "
        "FROM herman.coverage_assessments p JOIN herman.coverage_decisions d "
        "ON (d.business_id,d.assessment_id)=(p.business_id,p.id) "
        "WHERE p.business_id=%s AND p.warehouse_id=%s AND p.period_start=%s AND p.period_end=%s "
        "AND p.basis=%s AND d.approved AND NOT EXISTS (SELECT 1 FROM herman.coverage_decisions successor "
        "WHERE successor.business_id=p.business_id AND successor.supersedes_id=p.id AND successor.approved) "
        "ORDER BY p.id", (business, scope.warehouse_id, scope.start, scope.end, basis))
    if len(rows) > 1:
        raise ValueError("ارزیابی جاری پوشش یکتا نیست")
    assessment = proposal_from_row(rows[0]) if rows else None
    decision = CoverageReview(assessment_id=assessment.id, actor_id=rows[0]["actor_id"], approved=True,
        reason_fa=rows[0]["reason_fa"], decided_at=rows[0]["decided_at"], dataset=rows[0]["dataset"]) if rows else None
    as_of = c.execute("SELECT clock_timestamp() AS at").fetchone()["at"]
    return CoverageSnapshot(scope=scope, basis=basis, as_of=as_of, dataset=dataset,
                            assessment=assessment, decision=decision)
