# Operational metric contracts — proposed version 1

Each definition records an ID, version, unit, business/branch/warehouse scope, half-open period `[start, end)`, required inputs, formula, missing-data policy, evidence and review threshold. Inadequate coverage yields an incomplete result. Missing values are not zero.

## inventory.expected_usage.v1 — theoretical ingredient consumption

For each ingredient in its base unit:

`expected usage = sum(fulfilled production/service quantity × ingredient quantity in the recipe valid at that event time)`

For a net ingredient quantity, `raw quantity = net quantity / preparation yield`. Do not apply yield again when the recipe already specifies raw quantity. Cooking yield and preparation loss are different concepts. Batch recipes divide ingredient quantities by standard batch output. Expand nested recipes to base ingredients and reject cycles.

Canceled orders create no theoretical consumption. Prepared complimentary/staff meals do. A cash refund alone does not return physical ingredients to stock. Under a production-batch basis, ingredients are consumed by production; selling the resulting finished goods must not consume the ingredients again.

## inventory.expected_closing.v1 — expected closing stock

`opening + purchase receipts + inbound transfers − supplier returns − outbound transfers − recorded waste − other non-sale usage − theoretical usage`

Physical customer returns are inbound stock when evidenced; a monetary refund is not. Closing physical count is an independent observation, not an outbound movement. Do not include the adjustment derived from that count in expected stock before measuring variance, since doing so would conceal the discrepancy. Transfers can cancel at branch level while still affecting each warehouse.

## inventory.unexplained_variance.v1 — unexplained variance

`unexplained shortage = expected closing stock − counted closing stock`

Positive means shortage; negative means excess. `variance percentage = shortage / theoretical usage × 100`. When theoretical usage is zero, the relative variance is undefined, not zero or infinity.

Observed depletion can be calculated as opening stock plus inflows minus returns/outbound transfers minus closing stock. Compare it with theoretical use only after separating waste and other explained consumption.

Synthetic example: `100 kg opening + 50 kg purchases − 1,000 meals × 0.12 kg − 5 kg waste = 25 kg expected closing`. A count of 18 kg leaves a 7 kg unexplained shortage, approximately 5.83% of theoretical use. This does not establish cause: counting errors, recipe versions, portion size or missing receipts are possible explanations.

Required evidence: opening and closing counts with explicit cutoffs, all period movements, fulfilled service/production quantities, valid recipe versions, units and reviewed completeness assertions. A current stock count plus a recipe is insufficient.

## materiality.inventory_variance.v1 — review threshold

Each business supplies an absolute quantity threshold and a relative fraction. Flag when:

`abs(shortage) > max(absolute threshold, theoretical usage × relative threshold)`

Equality does not trigger a warning. This is a versioned operational-materiality rule, not statistical significance. Statistical interpretation needs sufficient history, measurement error and a variability model. Without a valid usage denominator, only an absolute threshold can be meaningful. Do not infer theft/fraud from one discrepancy or impose a universal threshold across industries.

## inventory.variance_value.v1 — variance value in IRR

`quantity variance × evidenced unit cost under the business's approved valuation method at the analysis date`

Record the method and cost version. The latest purchase price must not silently replace weighted-average or FIFO costing. If cost evidence is absent, report quantity only. This valuation metric remains a contract, not an implemented costing ledger.

## Additional initial metrics

| ID | Definition | Required data |
|---|---|---|
| inventory.waste_rate | Recorded waste / input to the relevant process | Reason, units and process; zero denominator is undefined. |
| recipe.standard_food_cost | Sum of raw ingredient quantity × unit cost / standard output | Recipe version and dated cost evidence. |
| product.gross_margin | (Net product revenue − cost of goods) / net revenue | Returns/discounts and compatible cost; operating expenses separate. |
| inventory.days_on_hand | Usable stock / average daily consumption in a stated window | Sufficient inventory/usage history; zero use is undefined. |
| data.coverage | Coverage of the evidence required by the question | Receipts, sales period, counts and applicable recipes. |

Direct supermarket SKU sales generally need no recipe; packs, returns, waste, expiry and counts matter. Cafes need coffee dose, milk, custom drinks and setup waste. Shared tools use industry-specific input contracts.
