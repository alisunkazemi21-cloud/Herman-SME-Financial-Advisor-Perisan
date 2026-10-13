"""Saved analysis, freshness and duplicates share the reviewed event-time definition."""

import hashlib
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from test_backend import backend as backend_fixture
from test_backend import database as database_fixture
from test_backend import inventory_payload as inventory_fixture
from test_backend import seed_inventory
from test_dated_inventory import BOUNDARY
from test_dated_inventory import dated_payload as dated_fixture
from test_inventory_corrections import analyze

from src.backend.advisor import BusinessAdvisor, BusinessContextInput
from src.backend.cases import BusinessCases, CaseInput, TurnInput
from src.backend.catalog import Catalog, PackDecision, PackProposal
from src.backend.inventory import Movement, UnitConversion
from src.backend.inventory_freshness import advice_summary, freshness
from src.backend.service import canonical

backend = backend_fixture
database = database_fixture
inventory_payload = inventory_fixture
dated_payload = dated_fixture


def setup(b, payload):
    p = payload["inventory"]
    start = datetime.now(timezone.utc)+timedelta(days=1)
    activation, end = start+timedelta(days=1), start+timedelta(days=2)
    for row in [p["opening"], p["closing"], *p["movements"], *p["fulfillments"]]:
        old = row["occurred_at"]
        row["occurred_at"] = (end if old == p["scope"]["end"] else
                              activation if old == BOUNDARY else start).isoformat()
    p["scope"].update(start=start.isoformat(), end=end.isoformat())
    value = seed_inventory(b, p)
    factor = UnitConversion(id=uuid4(), business_id=b["business"], item_id=value.target_item_id,
                            base_quantity="8", evidence=value.coverage.evidence)
    b["service"].catalog(b["owner"], b["business"], "baseline", factor)
    return p, value, factor, activation


def revise(b, factor, activation):
    catalog = Catalog(b["service"])
    value = PackProposal(id=uuid4(), item_id=factor.item_id, predecessor_id=factor.id,
                         base_quantity="10", evidence=factor.evidence)
    catalog.propose_pack(b["editor"], b["business"], "pack-proposal", value)
    catalog.decide_pack(b["owner"], b["business"], "pack-approval", value.id,
                       PackDecision(approved=True, reason_fa="نسخه جدید", effective_at=activation))
    return value.id


def test_analysis_receipt_freshness_legacy_and_source_lineage(backend, dated_payload):
    b = backend
    _, value, factor, activation = setup(b, dated_payload)
    old = analyze(b, value, "before")
    assert Decimal(old["result"]["unexplained_shortage"]) == 64
    assert len(old["pack_uses"]) == 6
    legacy = deepcopy(old)
    legacy["input_snapshot"].pop("pack_definitions")
    legacy["input_sha256"] = hashlib.sha256(canonical(legacy["input_snapshot"]).encode()).hexdigest()
    with b["db"].transaction(b["owner"], b["business"]) as c:
        assert freshness(c, b["business"], old)["status"] == "current"
        assert freshness(c, b["business"], legacy)["status"] == "current"
    cases = BusinessCases(b["service"], BusinessAdvisor(b["service"]))
    case = cases.create(b["owner"], b["business"], "case", CaseInput(title_fa="بررسی بسته"))
    turn = TurnInput(expected_turn=0, generate_draft=False, context=BusinessContextInput(
        question_fa="اختلاف چقدر است؟", effective_at=value.scope.end, analysis_id=old["id"]))

    def no_model(_):
        raise AssertionError("context-only turn must not call a model")

    first = cases.append(b["owner"], b["business"], case, "turn-1", turn, no_model)
    saved_turn = cases.read(b["viewer"], b["business"], case, first)
    assert len(saved_turn["receipt"]["context"]["analysis"]["pack_uses"]) == 6
    identity = revise(b, factor, activation)
    with b["db"].transaction(b["owner"], b["business"]) as c:
        assert freshness(c, b["business"], old)["status"] == "stale"
        assert freshness(c, b["business"], legacy)["status"] == "stale"
        assert advice_summary(c, b["business"], old)["result"] is None
    assert b["service"].analysis(b["viewer"], b["business"], old["id"]) == old
    second = cases.append(b["owner"], b["business"], case, "turn-2",
                          turn.model_copy(update={"expected_turn": 1}), no_model)
    assert cases.read(b["viewer"], b["business"], case, first) == saved_turn
    current = cases.read(b["viewer"], b["business"], case, second)["receipt"]["context"]["analysis"]
    assert current["result"] is None and current["pack_uses"] == []
    new = analyze(b, value, "after")
    assert Decimal(new["result"]["unexplained_shortage"]) == 58
    assert Decimal(new["result"]["expected_usage"]) == 18
    assert {u["definition_id"] for u in new["pack_uses"]} == {str(factor.id), str(identity)}
    with b["db"].transaction(b["owner"], b["business"]) as c:
        assert freshness(c, b["business"], new)["status"] == "current"


def test_duplicates_use_the_same_factor_on_both_sides_of_activation(backend, dated_payload):
    b = backend
    p, _, factor, activation = setup(b, dated_payload)
    revise(b, factor, activation)
    for index, (when, each) in enumerate(((p["scope"]["start"], "8"), (activation, "10"))):
        fields = dict(p["movements"][0], occurred_at=when, quantity="1", unit="pack")
        record = Movement.model_validate(dict(fields, id=str(uuid4())))
        b["service"].propose(b["editor"], b["business"], f"pack{index}", record)
        equivalent = Movement.model_validate(dict(fields, id=str(uuid4()), quantity=each, unit="each"))
        b["service"].propose(b["editor"], b["business"], f"each{index}", equivalent)
        candidates = b["service"].record(b["viewer"], b["business"], equivalent.id)["duplicate_candidates"]
        assert record.id in {row["id"] for row in candidates["records"]}
