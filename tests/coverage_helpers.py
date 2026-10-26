"""Explicit synthetic owner attestations for pre-C17 inventory fixtures.

This uses the public workflow and real review guards. It does not add a runtime
bypass or claim that a real business supplied these assertions.
"""

from uuid import uuid4

from src.backend.coverage import Coverage as CoverageWorkflow
from src.backend.coverage import CoverageDecision, CoverageProposal
from src.backend.coverage_models import CATEGORIES


def attest_coverage(b, value):
    workflow = CoverageWorkflow(b["service"])
    snapshot = workflow.assess(b["owner"], b["business"], value.scope, value.basis)
    if not snapshot.dataset.available:
        return None
    if (snapshot.decision is not None
            and snapshot.decision.dataset.signature == snapshot.dataset.signature):
        return snapshot.assessment.id
    categories = {}
    for category in CATEGORIES:
        count = snapshot.dataset.stats[category].event_count
        status = "records_complete" if count else "no_events"
        if category in ("opening_count", "closing_count") and not count:
            status = "missing"
        elif category == "recipes" and not count:
            status = "missing" if snapshot.dataset.required_recipe_products else "not_applicable"
        categories[category] = dict(
            status=status, evidence=value.coverage.evidence,
            note_fa="اظهار صریح مسئول نمونهٔ ساختگی؛ رکوردهای این دسته بررسی شدند.")
    proposal = CoverageProposal(
        id=uuid4(), scope=value.scope, basis=value.basis, categories=categories,
        evidence=value.coverage.evidence,
        supersedes_id=snapshot.assessment.id if snapshot.assessment is not None else None)
    workflow.propose(b["owner"], b["business"], "fixture-coverage:" + str(proposal.id), proposal)
    workflow.decide(b["owner"], b["business"], "fixture-coverage-review:" + str(proposal.id), proposal.id,
                    CoverageDecision(approved=True, reason_fa="بررسی صریح پوشش داده‌های ساختگی این دوره"))
    return proposal.id
