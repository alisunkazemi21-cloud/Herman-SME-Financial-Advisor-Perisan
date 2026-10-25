"""Independent historical interpretation and arithmetic; no database or model calls."""

from copy import deepcopy
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from test_dated_inventory import dated_payload as dated_fixture
from test_inventory import inventory_payload as inventory_fixture

from src.backend.pack_interpretation import (
    BoundInventoryRequest,
    BoundInventoryResult,
    InterpretedPackUse,
    PackContext,
    PackInterpreter,
    reconcile_bound_inventory,
)

inventory_payload = inventory_fixture
dated_payload = dated_fixture


@pytest.fixture
def bound_payload(dated_payload):
    p = dated_payload
    p["bindings"] = dict(
        business_id=p["inventory"]["scope"]["business_id"],
        as_of="2026-10-20T00:00:00Z",
        cutover_at="2026-08-01T00:00:00Z",
        legacy_record_ids=[],
        checks=[],
        resolutions=[],
        observations=[
            dict(definition_id=d["id"], observed_at="2026-08-15T00:00:00Z", origin="native_capture")
            for d in p["definitions"]
        ],
    )
    return p


def calculate(p):
    return reconcile_bound_inventory(BoundInventoryRequest.model_validate(p))


def opening_context(p):
    row = p["inventory"]["opening"]
    return dict(record_id=row["id"], item_id=row["item_id"], occurred_at=row["occurred_at"])


def unresolved(p, context=None):
    value = dict(
        id=str(uuid4()),
        business_id=p["bindings"]["business_id"],
        **(context or opening_context(p)),
        captured_at="2026-10-11T00:00:00Z",
        state="unresolved",
        origin="requires_review",
        missing_reason="missing_definition",
    )
    p["bindings"]["checks"].append(value)
    return value


def resolution(p, check, definition=None):
    value = dict(
        id=str(uuid4()),
        business_id=p["bindings"]["business_id"],
        check_id=check["id"],
        definition_id=definition or p["definitions"][0]["id"],
        actor_id=str(uuid4()),
        reason_fa="تبدیل تاریخی با سند بررسی شد",
        evidence=dict(document_id=str(uuid4()), locator="review:1"),
        decided_at="2026-10-12T00:00:00Z",
    )
    p["bindings"]["resolutions"].append(value)
    return value


def test_known_before_event_exact_arithmetic_and_versioned_receipts(bound_payload):
    p = bound_payload
    original = deepcopy(p)
    output = calculate(p)
    assert output.contract_version == "inventory.bound_pack.v1"
    assert output.result.unexplained_shortage == 58
    assert output.result.expected_usage == 18
    assert len(output.pack_uses) == 6
    assert all(
        u.context_version == "pack.use.v3" and u.interpretation == "known_before_event"
        for u in output.pack_uses
    )
    assert all(u.check_id is None and u.resolution_id is None for u in output.pack_uses)
    assert all(u.converted_quantity == u.quantity_pack * u.base_quantity for u in output.pack_uses)
    assert p == original


def test_late_baseline_never_implicitly_resolves_a_past_use(bound_payload):
    p = bound_payload
    p["bindings"]["observations"][0]["observed_at"] = "2026-10-10T00:00:00Z"
    result = calculate(p)
    assert result.result.status == "incomplete"
    assert result.result.unexplained_shortage is None
    assert result.pack_uses == ()


def test_unresolved_check_stays_sticky_even_with_known_before_definition(bound_payload):
    p = bound_payload
    unresolved(p)
    output = calculate(p)
    assert output.result.status == "incomplete" and output.pack_uses == ()
    assert output.result.expected_usage is None


def test_review_resolves_without_changing_original_check_and_includes_evidence(bound_payload):
    p = bound_payload
    check = unresolved(p)
    original = deepcopy(check)
    review = resolution(p, check)
    output = calculate(p)
    assert output.result.unexplained_shortage == 58
    use = next(u for u in output.pack_uses if str(u.record_id) == check["record_id"])
    assert str(use.check_id) == check["id"] and str(use.resolution_id) == review["id"]
    assert use.interpretation == "reviewed"
    assert use.resolution_evidence.model_dump(mode="json") == review["evidence"]
    assert use.resolution_evidence in output.result.evidence
    assert check == original


def test_bound_check_retains_identity_and_provenance(bound_payload):
    p = bound_payload
    check = dict(
        id=str(uuid4()),
        business_id=p["bindings"]["business_id"],
        **opening_context(p),
        captured_at="2026-10-11T00:00:00Z",
        definition_id=p["definitions"][0]["id"],
        state="bound",
        origin="known_before_event",
    )
    p["bindings"]["checks"] = [check]
    output = calculate(p)
    use = next(u for u in output.pack_uses if str(u.record_id) == check["record_id"])
    assert str(use.check_id) == check["id"] and use.interpretation == check["origin"]
    assert use.resolution_id is None


def test_legacy_baseline_is_qualified_migration_interpretation(bound_payload):
    p = bound_payload
    state, inv = p["bindings"], p["inventory"]
    state["cutover_at"] = "2026-10-10T00:00:00Z"
    state["observations"] = [
        dict(o, observed_at=state["cutover_at"], origin="migration_observation")
        for o in state["observations"]
    ]
    state["legacy_record_ids"] = [
        r["id"] for r in [inv["opening"], inv["closing"], *inv["movements"], *inv["fulfillments"]]
    ]
    output = calculate(p)
    assert output.result.unexplained_shortage == 58
    assert {u.interpretation for u in output.pack_uses} == {"migration_derived", "known_before_event"}
    # A baseline first observed natively after an event cannot borrow legacy provenance.
    state["observations"][0]["origin"] = "native_capture"
    assert calculate(p).result.status == "incomplete"


def test_future_revision_recalculates_64_to_58_and_preserves_prior_result(bound_payload):
    p = bound_payload
    p["bindings"]["as_of"] = "2026-09-10T00:00:00Z"
    newer = p["definitions"].pop()
    observation = p["bindings"]["observations"].pop()
    p["definitions"][0]["valid_to"] = None
    old = calculate(p)
    old_json = old.model_dump_json()
    assert old.result.unexplained_shortage == 64
    newer["approved_at"] = p["bindings"]["as_of"]
    p["definitions"].append(newer)
    p["bindings"]["observations"].append(observation)
    p["definitions"][0]["valid_to"] = newer["valid_from"]
    current = calculate(p)
    assert current.result.unexplained_shortage == 58
    assert any(u.interpretation == "deferred" for u in current.pack_uses)
    assert all(u.check_id is None for u in current.pack_uses if u.interpretation == "deferred")
    assert old.model_dump_json() == old_json


def test_unresolved_normalization_is_unavailable_even_for_equal_raw_packs(bound_payload):
    p = bound_payload
    check = unresolved(p)
    request = BoundInventoryRequest.model_validate(p)
    interpreter = PackInterpreter(request.definitions, request.bindings)
    context = PackContext.model_validate(opening_context(p))
    assert interpreter.normalize(Decimal(2), "pack", "each", context) is None
    assert interpreter.normalize(Decimal(2), "pack", "each", context) is None
    assert interpreter.normalize(Decimal(2), "kg", "g", context) == (Decimal(2000), "g")
    resolution(p, check)
    request = BoundInventoryRequest.model_validate(p)
    assert PackInterpreter(request.definitions, request.bindings).normalize(
        Decimal(2), "pack", "each", context
    ) == (Decimal(16), "each")


@pytest.mark.parametrize(
    "change",
    [
        "scope",
        "duplicate_observation",
        "missing_observation",
        "future_observation",
        "wrong_migration_time",
        "duplicate_check",
        "future_check",
        "future_approval",
        "orphan_review",
        "duplicate_review",
        "wrong_definition",
        "review_before_check",
        "bound_review",
        "false_provenance",
    ],
)
def test_invalid_metadata_cannot_become_numeric_output(bound_payload, change):
    p = bound_payload
    state = p["bindings"]
    check = unresolved(p)
    review = resolution(p, check)
    if change == "scope":
        state["business_id"] = str(uuid4())
    elif change == "duplicate_observation":
        state["observations"].append(deepcopy(state["observations"][0]))
    elif change == "missing_observation":
        state["observations"].pop()
    elif change == "future_observation":
        state["observations"][0]["observed_at"] = "2027-01-01T00:00:00Z"
    elif change == "wrong_migration_time":
        state["observations"][0]["origin"] = "migration_observation"
    elif change == "duplicate_check":
        state["checks"].append(dict(check, id=str(uuid4())))
    elif change == "future_check":
        check["captured_at"] = "2027-01-01T00:00:00Z"
    elif change == "future_approval":
        p["definitions"][1]["approved_at"] = "2027-01-01T00:00:00Z"
    elif change == "orphan_review":
        review["check_id"] = str(uuid4())
    elif change == "duplicate_review":
        state["resolutions"].append(dict(review, id=str(uuid4())))
    elif change == "wrong_definition":
        review["definition_id"] = p["definitions"][1]["id"]
    elif change == "review_before_check":
        review["decided_at"] = "2026-10-10T00:00:00Z"
    elif change == "bound_review":
        check.update(
            state="bound",
            origin="known_before_event",
            definition_id=p["definitions"][0]["id"],
            missing_reason=None,
        )
    else:
        state["resolutions"] = []
        check.update(
            state="bound",
            origin="migration_derived",
            definition_id=p["definitions"][0]["id"],
            missing_reason=None,
        )
    with pytest.raises((ValidationError, ValueError)):
        calculate(p)


@pytest.mark.parametrize("field", ["item_id", "occurred_at"])
def test_captured_key_with_contradictory_context_is_withheld(bound_payload, field):
    p = bound_payload
    context = opening_context(p)
    if field == "item_id":
        context[field] = p["inventory"]["items"][1]["id"]
    else:
        context[field] = "2026-09-02T00:00:00+03:30"
    unresolved(p, context)
    assert calculate(p).result.status == "incomplete"


def test_recipe_legacy_requires_every_ancestor_and_originating_fulfillment(bound_payload):
    p = bound_payload
    state, inv = p["bindings"], p["inventory"]
    product = inv["items"][1]["id"]
    recipe_id = str(uuid4())
    inv["recipes"] = [
        dict(
            id=recipe_id,
            business_id=state["business_id"],
            status="approved",
            evidence=inv["policy"]["evidence"],
            product_id=product,
            valid_from=inv["scope"]["start"],
            output_quantity="1",
            output_unit="each",
            lines=[dict(item_id=inv["target_item_id"], quantity="1", unit="pack")],
        )
    ]
    for row in inv["fulfillments"]:
        row.update(product_id=product, unit="each")
    state["cutover_at"] = "2026-10-10T00:00:00Z"
    state["observations"] = [
        dict(o, observed_at=state["cutover_at"], origin="migration_observation")
        for o in state["observations"]
    ]
    sources = [inv["opening"], inv["closing"], *inv["movements"], *inv["fulfillments"]]
    state["legacy_record_ids"] = [r["id"] for r in sources]
    assert calculate(p).result.status == "incomplete"
    state["legacy_record_ids"].append(recipe_id)
    output = calculate(p)
    assert output.result.expected_usage == 18
    uses = [u for u in output.pack_uses if str(u.record_id) == recipe_id]
    assert {u.fulfillment_id for u in uses} == {UUID(r["id"]) for r in inv["fulfillments"]}
    assert all(u.recipe_path == (UUID(recipe_id),) for u in uses)
    state["legacy_record_ids"].remove(inv["fulfillments"][0]["id"])
    assert calculate(p).result.status == "incomplete"


def test_result_has_no_partial_receipts_after_a_late_failure(bound_payload):
    p = bound_payload
    context = dict(
        record_id=p["inventory"]["movements"][-1]["id"],
        item_id=p["inventory"]["target_item_id"],
        occurred_at=p["inventory"]["movements"][-1]["occurred_at"],
    )
    unresolved(p, context)
    output = calculate(p)
    assert output.result.status == "incomplete" and output.pack_uses == ()
    assert output.result.counted_closing is None
    assert output.encountered_contexts[-1].record_id == UUID(context["record_id"])
    assert all(not hasattr(c, "quantity_pack") for c in output.encountered_contexts)


def test_timezone_equivalence_selects_the_same_half_open_interval(bound_payload):
    p = bound_payload
    p["inventory"]["movements"][1]["occurred_at"] = "2026-09-14T20:30:00Z"
    output = calculate(p)
    assert output.result.unexplained_shortage == 58
    assert datetime.fromisoformat(p["bindings"]["as_of"]).tzinfo is not None


@pytest.mark.parametrize("change", ["missing", "overlap", "gap", "proposed", "rejected"])
def test_no_unique_eligible_definition_never_produces_numbers(bound_payload, change):
    p = bound_payload
    newer = p["definitions"][1]
    if change == "missing":
        p["definitions"] = []
        p["bindings"]["observations"] = []
    elif change == "overlap":
        p["definitions"][0]["valid_to"] = None
    elif change == "gap":
        newer["valid_from"] = "2026-09-16T00:00:00+03:30"
    else:
        newer.update(decision=change, approved_at=None)
    output = calculate(p)
    assert output.result.status == "incomplete"
    assert output.pack_uses == () and output.result.unexplained_shortage is None


def test_new_receipt_roundtrip_and_no_invented_review_context(bound_payload):
    p = bound_payload
    output = calculate(p)
    assert BoundInventoryResult.model_validate_json(output.model_dump_json()) == output
    use = output.pack_uses[0].model_dump(mode="json")
    with pytest.raises(ValidationError):
        InterpretedPackUse.model_validate(dict(use, interpretation="reviewed"))
    with pytest.raises(ValidationError):
        InterpretedPackUse.model_validate(dict(use, resolution_id=str(uuid4())))
    unresolved(p)
    incomplete = calculate(p)
    with pytest.raises(ValidationError):
        BoundInventoryResult(result=incomplete.result, pack_uses=output.pack_uses)


def test_zero_quantity_does_not_bypass_review_and_dimensions_stay_explicit(bound_payload):
    p = bound_payload
    unresolved(p)
    request = BoundInventoryRequest.model_validate(p)
    interpreter = PackInterpreter(request.definitions, request.bindings)
    context = PackContext.model_validate(opening_context(p))
    assert interpreter.normalize(Decimal(0), "pack", "each", context) is None
    assert interpreter.normalize(Decimal(2), "kg", "ml", context) is None
    assert interpreter.normalize(Decimal(2), "each", "each", context) == (Decimal(2), "each")
    with pytest.raises(ValueError):
        interpreter.normalize(float(2), "each", "each", context)


def test_definition_must_exist_by_resolution_time_and_later_review_is_allowed(bound_payload):
    p = bound_payload
    check = unresolved(p)
    review = resolution(p, check)
    p["bindings"]["observations"][0]["observed_at"] = "2026-10-15T00:00:00Z"
    with pytest.raises(ValidationError):
        BoundInventoryRequest.model_validate(p)
    review["decided_at"] = "2026-10-16T00:00:00Z"
    request = BoundInventoryRequest.model_validate(p)
    selected = PackInterpreter(request.definitions, request.bindings).select(
        PackContext.model_validate(opening_context(p))
    )
    assert selected.interpretation == "reviewed" and str(selected.resolution_id) == review["id"]


@pytest.mark.parametrize(
    "change",
    [
        "native_migration",
        "review_before_consumption",
        "observation_after_review",
        "wrong_arithmetic",
        "negative_quantity",
        "missing_result_evidence",
    ],
)
def test_receipt_provenance_and_numbers_cannot_contradict_their_inputs(bound_payload, change):
    p = bound_payload
    check = unresolved(p)
    resolution(p, check)
    output = calculate(p)
    use = next(u for u in output.pack_uses if u.interpretation == "reviewed").model_dump(mode="json")
    if change == "native_migration":
        use.update(
            interpretation="migration_derived",
            resolution_id=None,
            resolution_evidence=None,
            resolution_decided_at=None,
        )
    elif change == "review_before_consumption":
        use["resolution_decided_at"] = "2026-08-30T00:00:00Z"
    elif change == "observation_after_review":
        use["observed_at"] = "2026-10-15T00:00:00Z"
    elif change == "wrong_arithmetic":
        use["converted_quantity"] = "999"
    elif change == "negative_quantity":
        use["quantity_pack"] = "-1"
    else:
        with pytest.raises(ValidationError):
            BoundInventoryResult(
                result=output.result.model_copy(update={"evidence": ()}), pack_uses=output.pack_uses
            )
        return
    with pytest.raises(ValidationError):
        InterpretedPackUse.model_validate(use)


@pytest.mark.parametrize("missing_index", range(4))
def test_nested_legacy_path_requires_each_source_flag(bound_payload, missing_index):
    p = bound_payload
    state = p["bindings"]
    path = [str(uuid4()) for _ in range(3)]
    fulfillment = str(uuid4())
    state["cutover_at"] = "2026-10-10T00:00:00Z"
    state["observations"] = [
        dict(o, observed_at=state["cutover_at"], origin="migration_observation")
        for o in state["observations"]
    ]
    state["legacy_record_ids"] = [*path, fulfillment]
    context = PackContext(
        record_id=path[-1],
        fulfillment_id=fulfillment,
        recipe_path=path,
        ingredient_id=p["inventory"]["target_item_id"],
        item_id=p["inventory"]["target_item_id"],
        occurred_at=p["inventory"]["scope"]["start"],
    )
    request = BoundInventoryRequest.model_validate(p)
    interpreter = PackInterpreter(request.definitions, request.bindings)
    assert interpreter.normalize(Decimal(1), "pack", "each", context) == (Decimal(8), "each")
    state["legacy_record_ids"].pop(missing_index)
    request = BoundInventoryRequest.model_validate(p)
    assert (
        PackInterpreter(request.definitions, request.bindings).normalize(Decimal(1), "pack", "each", context)
        is None
    )


def test_incomplete_conversion_keeps_a_nonnumeric_context_for_later_write_capture(bound_payload):
    p = bound_payload
    first = p["inventory"]["fulfillments"][0]
    context = dict(
        record_id=first["id"],
        fulfillment_id=first["id"],
        item_id=first["product_id"],
        occurred_at=first["occurred_at"],
    )
    unresolved(p, context)
    output = calculate(p)
    assert output.result.status == "incomplete" and output.pack_uses == ()
    assert output.encountered_contexts == (PackContext.model_validate(context),)


def test_pack_context_budget_yields_incomplete_without_partial_numeric_receipts(bound_payload):
    p = bound_payload
    first = p["inventory"]["fulfillments"][0]
    p["inventory"]["fulfillments"] = [dict(first, id=str(uuid4())) for _ in range(10000)]
    output = calculate(p)
    assert output.result.status == "incomplete" and output.result.expected_usage is None
    assert output.pack_uses == () and len(output.encountered_contexts) == 10000
