from copy import deepcopy
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError
from test_inventory import inventory_payload as inventory_fixture

from src.backend.dated_inventory import DatedInventoryRequest, reconcile_dated_inventory
from src.backend.inventory import InventoryRequest, reconcile_inventory

inventory_payload = inventory_fixture
BOUNDARY = "2026-09-15T00:00:00+03:30"


@pytest.fixture
def dated_payload(inventory_payload):
    p = inventory_payload
    item = p["target_item_id"]
    p["items"][0]["base_unit"] = "each"
    p["opening"].update(quantity="10", unit="pack")
    p["closing"].update(quantity="5", unit="pack")
    p["movements"] = [dict(p["opening"], id=str(uuid4()), quantity="2", kind="purchase"),
                      dict(p["opening"], id=str(uuid4()), quantity="3", kind="purchase",
                           occurred_at=BOUNDARY)]
    p["recipes"] = []
    p["fulfillments"][0].update(product_id=item, quantity="1", unit="pack")
    p["fulfillments"].append(dict(p["fulfillments"][0], id=str(uuid4()), occurred_at=BOUNDARY))
    common = dict(business_id=p["scope"]["business_id"], item_id=item,
                  evidence=p["policy"]["evidence"])
    definitions = [dict(common, id=str(uuid4()), base_quantity="8", decision="baseline",
                        valid_to=BOUNDARY),
                   dict(common, id=str(uuid4()), base_quantity="10", decision="approved",
                        valid_from=BOUNDARY, approved_at=BOUNDARY)]
    return dict(inventory=p, definitions=definitions)


def calculate(payload):
    return reconcile_dated_inventory(DatedInventoryRequest.model_validate(payload))


def test_crossing_activation_exact_arithmetic_and_receipts(dated_payload):
    original = deepcopy(dated_payload)
    output = calculate(dated_payload)
    result = output.result
    assert result.status == "complete"
    # 10*8 + 2*8 + 3*10 - (1*8 + 1*10) - 5*10 = 58.
    assert result.expected_usage == 18
    assert result.expected_closing == 108
    assert result.counted_closing == 50
    assert result.unexplained_shortage == 58
    assert len(output.pack_uses) == 6
    lookup = {str(row.record_id): row for row in output.pack_uses}
    p = dated_payload["inventory"]
    assert lookup[p["opening"]["id"]].base_quantity == 8
    assert lookup[p["closing"]["id"]].base_quantity == 10
    for use in output.pack_uses:
        assert use.converted_quantity == use.quantity_pack * use.base_quantity
        assert use.evidence in result.evidence
    assert dated_payload == original


@pytest.mark.parametrize("kind", ["gap", "overlap", "missing", "pending", "rejected"])
def test_no_unique_eligible_definition_means_no_numbers(dated_payload, kind):
    newer = dated_payload["definitions"][1]
    if kind == "gap":
        newer["valid_from"] = "2026-09-16T00:00:00+03:30"
    elif kind == "overlap":
        dated_payload["definitions"][0]["valid_to"] = None
    elif kind == "missing":
        dated_payload["definitions"] = []
    else:
        newer.update(decision="proposed" if kind == "pending" else kind, approved_at=None)
    output = calculate(dated_payload)
    assert output.result.status == "incomplete"
    assert output.result.unexplained_shortage is None
    assert output.result.expected_usage is None
    assert output.pack_uses == ()


@pytest.mark.parametrize("decision", ["proposed", "rejected"])
def test_competing_unapproved_candidate_does_not_change_result(dated_payload, decision):
    before = calculate(dated_payload)
    candidate = dict(dated_payload["definitions"][1], id=str(uuid4()),
                     decision=decision, approved_at=None, base_quantity="999")
    dated_payload["definitions"].append(candidate)
    assert calculate(dated_payload) == before


def test_utc_boundary_and_backdated_event_choose_original_factor(dated_payload):
    p = dated_payload["inventory"]
    p["movements"][1]["occurred_at"] = "2026-09-14T20:30:00Z"
    assert calculate(dated_payload).result.unexplained_shortage == 58
    p["movements"][1]["occurred_at"] = "2026-09-14T20:29:59.999999Z"
    output = calculate(dated_payload)
    assert output.result.unexplained_shortage == 52
    use = next(row for row in output.pack_uses if str(row.record_id) == p["movements"][1]["id"])
    assert str(use.definition_id) == dated_payload["definitions"][0]["id"]


def test_recipe_ingredient_uses_fulfillment_instant(dated_payload):
    p = dated_payload["inventory"]
    product = p["items"][1]["id"]
    recipe = dict(id=str(uuid4()), business_id=p["scope"]["business_id"], status="approved",
                  evidence=p["policy"]["evidence"], product_id=product,
                  valid_from=p["scope"]["start"], output_quantity="1", output_unit="each",
                  lines=[dict(item_id=p["target_item_id"], quantity="1", unit="pack")])
    p["recipes"] = [recipe]
    for row in p["fulfillments"]:
        row.update(product_id=product, unit="each")
    output = calculate(dated_payload)
    assert output.result.expected_usage == 18
    uses = [row for row in output.pack_uses if str(row.record_id) == recipe["id"]]
    assert [row.base_quantity for row in uses] == [8, 10]
    assert all(str(row.ingredient_id) == p["target_item_id"] for row in uses)
    assert [row.quantity_base for row in output.result.contributions] == [8, 10]


def test_recipe_output_pack_uses_event_instant(dated_payload):
    p = dated_payload["inventory"]
    product = p["items"][1]["id"]
    p["recipes"] = [dict(id=str(uuid4()), business_id=p["scope"]["business_id"],
                         status="approved", evidence=p["policy"]["evidence"], product_id=product,
                         valid_from=p["scope"]["start"], output_quantity="1", output_unit="pack",
                         lines=[dict(item_id=p["target_item_id"], quantity="80", unit="each")])]
    for row in p["fulfillments"]:
        row.update(product_id=product, unit="each", quantity="1")
    dated_payload["definitions"].extend(
        [dict(row, id=str(uuid4()), item_id=product) for row in dated_payload["definitions"]])
    output = calculate(dated_payload)
    assert output.result.expected_usage == 18  # 80/8 + 80/10.
    assert [row.quantity_base for row in output.result.contributions] == [10, 8]


@pytest.mark.parametrize("change", ["tenant", "item", "duplicate", "backdate", "naive",
                                    "float", "zero", "reversed", "baseline_approval", "mixed"])
def test_invalid_definitions_rejected(dated_payload, change):
    row = dated_payload["definitions"][1]
    if change == "tenant":
        row["business_id"] = str(uuid4())
    elif change == "item":
        row["item_id"] = str(uuid4())
    elif change == "duplicate":
        dated_payload["definitions"].append(deepcopy(row))
    elif change == "backdate":
        row["approved_at"] = "2026-09-16T00:00:00+03:30"
    elif change == "naive":
        row["valid_from"] = "2026-09-15T00:00:00"
    elif change == "float":
        row["base_quantity"] = 0.1
    elif change == "zero":
        row["base_quantity"] = "0"
    elif change == "reversed":
        row["valid_to"] = row["valid_from"]
    elif change == "baseline_approval":
        dated_payload["definitions"][0]["approved_at"] = BOUNDARY
    else:
        dated_payload["inventory"]["conversions"] = [dict(
            id=str(uuid4()), business_id=row["business_id"], item_id=row["item_id"],
            base_quantity="10", evidence=row["evidence"])]
    with pytest.raises(ValidationError):
        calculate(dated_payload)


def test_legacy_serialization_and_result_unchanged(inventory_payload):
    legacy = InventoryRequest.model_validate(inventory_payload)
    before = legacy.model_dump_json()
    expected = reconcile_inventory(legacy)
    output = reconcile_dated_inventory(DatedInventoryRequest(inventory=legacy))
    assert output.result == expected
    assert output.pack_uses == ()
    assert legacy.model_dump_json() == before
    assert "definitions" not in before


def test_exact_decimal_factor_and_snapshot_immutability(dated_payload):
    dated_payload["definitions"][0]["base_quantity"] = "8.123456"
    before = calculate(dated_payload)
    receipt = before.model_dump_json()
    assert before.result.expected_usage == Decimal("18.123456")
    dated_payload["definitions"][1]["base_quantity"] = "20"
    assert calculate(dated_payload).result.expected_usage == Decimal("28.123456")
    assert before.model_dump_json() == receipt


def test_wrong_dimension_is_not_a_pack_conversion(dated_payload):
    dated_payload["inventory"]["opening"]["unit"] = "kg"
    output = calculate(dated_payload)
    assert output.result.status == "incomplete"
    assert output.pack_uses == ()
