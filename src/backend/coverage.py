"""Tenant-scoped immutable completeness proposals and human decisions."""

from uuid import UUID

from psycopg.types.json import Jsonb

from src.backend.coverage_budget import coverage_budget
from src.backend.coverage_models import CoverageDecision, CoverageProposal, CoverageSnapshot
from src.backend.coverage_selection import proposal_from_row, select_coverage
from src.backend.inventory import Scope
from src.backend.service import NotFound, Service, insert

__all__ = ["Coverage", "CoverageProposal", "CoverageDecision"]


class Coverage:
    def __init__(self, service: Service):
        self.service = service

    def propose(self, actor: UUID, business: UUID, key: str, value: CoverageProposal) -> UUID:
        if value.scope.business_id != business:
            raise ValueError("ارزیابی متعلق به کسب‌وکار دیگری است")

        def store(c):
            refs = [value.evidence, *(entry.evidence for entry in value.categories.values() if entry.evidence)]
            for document in {ref.document_id for ref in refs}:
                self.service._inventory_evidence(c, business, document)
            insert(c, "coverage_assessments", dict(business_id=business, id=value.id,
                warehouse_id=value.scope.warehouse_id, period_start=value.scope.start, period_end=value.scope.end,
                basis=value.basis, categories=Jsonb({name: entry.model_dump(mode="json")
                    for name, entry in value.categories.items()}), document_id=value.evidence.document_id,
                locator=value.evidence.locator, supersedes_id=value.supersedes_id, created_by=actor))
            return value.id

        return self.service._write(actor, business, key, "coverage.proposed", value.model_dump(mode="json"), store)

    def decide(self, actor: UUID, business: UUID, key: str, identity: UUID, value: CoverageDecision) -> UUID:
        def store(c):
            row = c.execute("SELECT * FROM herman.coverage_assessments WHERE business_id=%s AND id=%s",
                            (business, identity)).fetchone()
            if row is None:
                raise NotFound("ارزیابی موجود نیست")
            if value.approved:
                proposal = proposal_from_row(row)
                snapshot = select_coverage(c, business, proposal.scope, proposal.basis)
                refs = [proposal.evidence, *(entry.evidence for entry in proposal.categories.values() if entry.evidence),
                        *snapshot.dataset.evidence_refs]
                for document in {ref.document_id for ref in refs}:
                    self.service._inventory_evidence(c, business, document)
            with coverage_budget(c):
                insert(c, "coverage_decisions", dict(business_id=business, assessment_id=identity,
                    actor_id=actor, **value.model_dump()))
            return identity

        return self.service._write(actor, business, key, "coverage.reviewed",
            dict(id=str(identity), **value.model_dump(mode="json")), store, reviewer=True)

    def page(self, actor: UUID, business: UUID, after: UUID | None = None, limit: int = 50) -> dict:
        if not 1 <= limit <= 100:
            raise ValueError("اندازهٔ صفحه نامعتبر است")
        with self.service.database.transaction(actor, business) as c:
            rows = c.execute("SELECT p.*,d.approved,d.actor_id,d.decided_at,d.reason_fa,"
                "successor.assessment_id AS successor_id FROM herman.coverage_assessments p "
                "LEFT JOIN herman.coverage_decisions d ON (d.business_id,d.assessment_id)=(p.business_id,p.id) "
                "LEFT JOIN herman.coverage_decisions successor ON successor.business_id=p.business_id "
                "AND successor.supersedes_id=p.id AND successor.approved "
                "WHERE p.business_id=%s AND (%s::uuid IS NULL OR p.id>%s) ORDER BY p.id LIMIT %s",
                (business, after, after, limit + 1)).fetchall()
            return dict(assessments=rows[:limit], next_cursor=rows[limit-1]["id"] if len(rows)>limit else None,
                        evidence_verification="not_rechecked")

    def detail(self, actor: UUID, business: UUID, identity: UUID) -> dict:
        with self.service.database.transaction(actor, business) as c:
            row = c.execute("SELECT * FROM herman.coverage_assessments WHERE business_id=%s AND id=%s",
                            (business, identity)).fetchone()
            if row is None:
                raise NotFound("ارزیابی موجود نیست")
            decision = c.execute("SELECT * FROM herman.coverage_decisions WHERE business_id=%s AND assessment_id=%s",
                                 (business, identity)).fetchone()
            successor = c.execute("SELECT assessment_id FROM herman.coverage_decisions WHERE business_id=%s "
                                  "AND supersedes_id=%s AND approved", (business, identity)).fetchone()
            return dict(assessment=proposal_from_row(row).model_dump(), created_by=row["created_by"],
                created_at=row["created_at"], decision=decision,
                successor_id=successor["assessment_id"] if successor else None, evidence_verification="not_rechecked")

    def assess(self, actor: UUID, business: UUID, scope: Scope, basis: str) -> CoverageSnapshot:
        with self.service.database.transaction(actor, business) as c:
            return select_coverage(c, business, scope, basis)
