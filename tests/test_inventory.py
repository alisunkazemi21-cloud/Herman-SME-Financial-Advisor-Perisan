from copy import deepcopy
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.backend.inventory import InventoryRequest, reconcile_inventory


@pytest.fixture
def inventory_payload():
    business, warehouse, meat, meal, document = [str(uuid4()) for _ in range(5)]
    evidence = {"document_id": document, "locator": "sheet1!A2"}
    start, end = "2026-09-01T00:00:00+03:30", "2026-10-01T00:00:00+03:30"

    def record(**fields):
        return dict(id=str(uuid4()), business_id=business, evidence=evidence,
                    status="approved", **fields)

    def count(quantity, when):
        return record(warehouse_id=warehouse, item_id=meat, occurred_at=when, quantity=quantity, unit="kg")

    return {
        "scope": dict(business_id=business, warehouse_id=warehouse, start=start, end=end),
        "target_item_id": meat,
        "items": [dict(id=meat, business_id=business, sku="MEAT", name_fa="گوشت", base_unit="g"),
                  dict(id=meal, business_id=business, sku="MEAL", name_fa="غذا", base_unit="each",
                       consumption_mode="recipe")],
        "opening": count("100", start), "closing": count("18", end),
        "movements": [dict(**count("50", start), kind="purchase"),
                      dict(**count("5", start), kind="waste")],
        "recipes": [record(product_id=meal, valid_from=start, output_quantity="1", output_unit="each",
                           lines=[dict(item_id=meat, quantity="0.12", unit="kg")])],
        "fulfillments": [record(warehouse_id=warehouse, product_id=meal, occurred_at=start,
                                quantity="1000", unit="each")],
        "coverage": dict(movements_complete=True, fulfillment_complete=True, recipes_complete=True,
                         evidence=evidence),
        "policy": dict(absolute_base_quantity="1000", relative_fraction="0.05", evidence=evidence),
    }


def calculate(payload):
    return reconcile_inventory(InventoryRequest.model_validate(payload))


def test_restaurant_provenance_and_exact_arithmetic(inventory_payload):
    result = calculate(inventory_payload)
    assert result.status == "complete"
    assert result.expected_usage == Decimal("120000")
    assert result.expected_closing == Decimal("25000")
    assert result.unexplained_shortage == Decimal("7000")
    assert result.materiality_threshold == Decimal("6000")
    assert result.needs_review
    assert str(result.contributions[0].recipe_ids[0]) == inventory_payload["recipes"][0]["id"]
    assert result.contributions[0].evidence


@pytest.mark.parametrize("change", ["opening", "coverage", "unapproved", "double_use", "mixed_basis",
                                    "recipe_missing", "unit", "overlap", "cycle", "intermediate"])
def test_incomplete_never_reports_shortage(inventory_payload, change):
    p = inventory_payload
    if change == "opening":
        p["opening"] = None
    elif change == "coverage":
        p["coverage"]["movements_complete"] = False
    elif change == "unapproved":
        p["opening"]["status"] = "proposed"
    elif change == "double_use":
        p["movements"][0]["kind"] = "count_adjustment"
    elif change == "mixed_basis":
        p["fulfillments"][0]["kind"] = "production"
    elif change == "recipe_missing":
        p["recipes"] = []
    elif change == "unit":
        p["opening"]["unit"] = "l"
    elif change == "overlap":
        other = deepcopy(p["recipes"][0])
        other["id"] = str(uuid4())
        p["recipes"].append(other)
    elif change == "cycle":
        p["recipes"][0]["lines"][0]["item_id"] = p["items"][1]["id"]
        p["recipes"][0]["lines"][0]["unit"] = "each"
    else:
        p["items"][0]["consumption_mode"] = "recipe"
    result = calculate(p)
    assert result.status == "incomplete"
    assert result.unexplained_shortage is None
    assert result.needs_review is None
    assert result.missing_fa


@pytest.mark.parametrize("change", ["tenant", "warehouse", "date", "float", "precision", "duplicate",
                                    "negative", "yield"])
def test_malformed_data_rejected(inventory_payload, change):
    p = inventory_payload
    if change == "tenant":
        p["recipes"][0]["business_id"] = str(uuid4())
    elif change == "warehouse":
        p["movements"][0]["warehouse_id"] = str(uuid4())
    elif change == "date":
        p["fulfillments"][0]["occurred_at"] = p["scope"]["end"]
    elif change == "float":
        p["opening"]["quantity"] = 0.1
    elif change == "precision":
        p["opening"]["quantity"] = "0.1234567"
    elif change == "duplicate":
        p["movements"].append(p["movements"][0])
    elif change == "negative":
        p["closing"]["quantity"] = "-1"
    else:
        p["recipes"][0]["lines"][0]["preparation_yield"] = "0.8"
    with pytest.raises(ValidationError):
        calculate(p)


def test_nested_recipe_batch_yield_and_timestamp_version(inventory_payload):
    p = inventory_payload
    prepared = str(uuid4())
    p["items"].append(dict(id=prepared, business_id=p["scope"]["business_id"], sku="PREP",
                           name_fa="مواد آماده", base_unit="g", consumption_mode="recipe"))
    original = p["recipes"][0]
    nested = deepcopy(original)
    nested.update(id=str(uuid4()), product_id=prepared, output_quantity="1000", output_unit="g")
    nested["lines"][0].update(quantity="0.8", basis="net", preparation_yield="0.8")
    original["lines"] = [dict(item_id=prepared, quantity="120", unit="g")]
    original["valid_to"] = "2026-09-15T00:00:00+03:30"
    newer = deepcopy(original)
    newer.update(id=str(uuid4()), valid_from=original["valid_to"], valid_to=None)
    newer["lines"][0]["quantity"] = "150"
    p["recipes"].extend([nested, newer])
    first = p["fulfillments"][0]
    first["quantity"] = "500"
    second = dict(first, id=str(uuid4()), occurred_at=original["valid_to"])
    p["fulfillments"].append(second)
    result = calculate(p)
    assert result.status == "complete"
    assert result.expected_usage == Decimal("135000")
    assert len(result.contributions[0].recipe_ids) == 2
    assert str(result.contributions[1].recipe_ids[0]) == newer["id"]


def test_retail_pack_conversion_and_zero_denominator(inventory_payload):
    p = inventory_payload
    meat = p["items"][0]["id"]
    p["fulfillments"][0].update(product_id=meat, quantity="2", unit="pack")
    p["conversions"] = [dict(id=str(uuid4()), business_id=p["scope"]["business_id"], item_id=meat,
                              base_quantity="60000", evidence=p["policy"]["evidence"])]
    assert calculate(p).expected_usage == Decimal("120000")
    p["fulfillments"][0]["fulfilled"] = False
    result = calculate(p)
    assert result.expected_usage == 0
    assert result.variance_fraction is None


def test_materiality_boundary_and_excess(inventory_payload):
    p = inventory_payload
    p["closing"]["quantity"] = "19"
    assert calculate(p).needs_review is False  # exactly 5%, strict greater-than
    p["closing"]["quantity"] = "32"
    result = calculate(p)
    assert result.unexplained_shortage == Decimal("-7000")
    assert result.needs_review is True
