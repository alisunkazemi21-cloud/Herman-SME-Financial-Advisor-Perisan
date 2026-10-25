# Pricing and product contribution — dashboard contract

Requested October 25, 2026. **Designed; calculator, persistence, routes and owner screen are not implemented.** This extends the business portfolio without replacing its five existing financial indicators. Backend integrity and C16 remain the current implementation priority.

## Owner questions and planned presentation

| Persian app section | Question answered | Planned data |
|---|---|---|
| بهای تمام‌شده | What does one sellable unit cost? | Ingredients, packaging, preparation labor, variable operations, normal loss and separately allocated shared costs, with evidence links. |
| سناریوهای قیمت‌گذاری | What prices cover the chosen costs and margin? | Current price, calculated scenario, desired margin, channel fees, competitor observations and customer price evidence. |
| اقلام و فعالیت‌های کلیدی | Which products and activities contribute most? | Unit/total contribution, volume, attributable result, preparation time and the cost or capacity drivers behind them. |

Show status, as-of time, costing basis, source/recipe versions and missing inputs beside each figure. A cost waterfall and a price/contribution comparison can use the same typed results later; a visual without its required reviewed data must show an unavailable state. Prices remain owner-reviewed scenarios. Do not automatically change a menu, post a journal, or call a scenario an optimal price.

## Input and history contract

Use tenant-scoped, append-only proposals and separate decisions, following existing inventory/portfolio roles and idempotency. Each calculation snapshot must preserve the selected source IDs, source hashes, versions, exact decimal inputs, formula version and assumptions. Later corrections produce a new calculation; earlier results remain readable. Reads cannot manufacture missing prices or approve assumptions.

Each scenario needs business, product/item ID, recipe version/path where applicable, sales channel, serving/pack size, aware effective instant, half-open reporting period, currency and cost basis. Distinguish a forward replacement-cost pricing scenario from realized period contribution under a reviewed historical costing method. A recent invoice is not automatically a FIFO or weighted-average valuation ledger. Shared ingredient costs do not establish product selling prices.

Amounts use exact Decimal strings and the backend's canonical **IRR**. Explicit toman input is converted once at the intake boundary with original value/unit retained; never guess the unit from its magnitude. Quantities and recipe yields retain their physical units. Resolve pack factors and recipes under accepted C16 history rules; unresolved conversions block dependent cost figures. Public pricing routes must wait for those controls.

| Input | Required provenance / semantics |
|---|---|
| Raw materials | Reviewed purchase or supplier quote, acquisition costs/discounts, physical quantity/unit, applicable dates and declared historical/replacement method. Recoverable tax is separate from cost; no tax rate is assumed. |
| Recipe and sellable output | Evidenced version, gross/raw versus net ingredient basis, batch output, preparation yield and normal saleable yield. Support direct resale items without a recipe. |
| Packaging | Item, amount consumed per sold unit, dated unit cost and channel; include bags, cups or containers only where actually required. |
| Waste | Explicit stage, denominator and basis: already included in raw recipe, preparation yield, saleable batch yield, or an additional evidenced normal loss. Record actual abnormal/unexplained loss separately. |
| Preparation and operations | Activity, unit/batch/period basis, labor minutes and evidenced hourly rate or other cost driver; classify variable versus fixed and production versus other business costs. Owner labor cannot silently default to free. |
| Shared costs | Period cost pool, included categories, documented driver/capacity, denominator and allocation version. Keep unallocated residual visible and reconcile allocations to pools. |
| Sale and fees | Channel-specific price basis, discounts/refunds, tax treatment, fee structure/base, fixed per-order fees and units per order. Do not silently assume one item per order. |
| Margin target | Explicit owner target and named cost basis, effective dates, and whether percentage fees are included. Targets are assumptions, not achieved results. |
| Competitor observation | Source/menu/quote, observed date, comparable size/quality/location/channel, currency, tax/promotion/delivery treatment and review status. Retain individual observations; do not infer a market range from incomparable items. |
| Customer price evidence | Consented aggregate interview/survey or actual transaction/experiment, segment/channel, dates, sample size, question/method and price interval. An owner's estimate is labeled an assumption. No supported evidence means unknown willingness to pay. |
| Realized volume/result | Net sales, discounts/returns and fulfilled quantities for the same period/channel; period costs and capacity evidence for any period or activity ranking. Forecast volume is labeled a scenario. |

Completeness is per metric. An explicit reviewed zero is different from a missing expense. Stale cost/competitor/customer evidence gets a visible stale state under a declared freshness policy, not an invented universal expiry. Conflicting reviewed inputs stay conflicting until resolved. Inventory reconciliation alone cannot populate monetary cost or demand evidence.

## Deterministic calculations

1. **Ingredients:** sum the dated cost of the raw quantities needed for the evidenced saleable output. For net quantity `q` and preparation yield `y`, raw input is `q / y`, with `0 < y <= 1`; if the recipe already states gross raw input, do not apply that yield again. For a batch, divide eligible batch costs by its explicit sellable output. A saleable-output loss already incorporated in that denominator cannot be charged again as a waste percentage. Never infer a monetary waste charge from an unexplained inventory variance.
2. **Variable unit cost `V`:** eligible ingredients + packaging + variable preparation/operating costs + other explicitly attributable variable costs, before percentage-of-price fees. Preserve a component breakdown. Period fixed expenses remain separate.
3. **Allocated scenario cost `C`:** `V + allocated shared cost per sellable unit` when the full allocation is supplied. Report the allocation method and capacity assumption. This managerial scenario is separate from accounting inventory valuation and is not called verified net profit or standards compliance.
4. **Contribution:** for comparable net-of-tax/discount unit selling price `P` and percentage fee `f` charged on that same base, `unit contribution = P * (1 - f) - V`; contribution fraction is that result divided by positive `P`. With other fee bases, use the explicit fee function rather than this simplified formula. Do not deduct fixed overhead twice.
5. **Target price:** for the explicitly selected cost basis `C`, target margin fraction `m` after the same percentage fee, `P = C / (1 - m - f)`. Require nonnegative costs/fees, `0 <= m < 1` and a positive denominator. A zero-cost scenario is not evidence that all costs were supplied. With no percentage fee, `P = C / (1 - m)`. Markup is a separate setting: `P = C * (1 + markup)` under its stated fee assumptions. A 30% margin is not a 30% markup.
6. **Realized product contribution:** comparable net revenue less attributable variable costs and actual channel fees for the period. A calculated `unit contribution * volume` is valid only for a uniform compatible price/cost scenario; otherwise sum the event-level amounts. Show attributed fixed allocations separately from contribution and retain unapportioned expenses.
7. **Activity/resource view:** contribution per evidenced preparation or bottleneck minute is a comparison aid when that resource is constrained and the denominator is positive. Actual activity cost, throughput, idle capacity and scenario effects are separate fields. A high ratio alone does not establish demand, feasibility or a reason to remove another product.

For allocated-cost price scenarios, show sensitivity to explicit volume/capacity assumptions rather than presenting one allocation denominator as certain. Stale historical scenarios remain inspectable, but stale or unresolved critical inputs withhold a current actionable price recommendation until reviewed.

Use enough internal decimal precision for division and retain the unrounded scenario. Apply an explicit display/menu rounding increment once, then recompute achieved margin on the rounded proposed price. No float arithmetic or silent tax/rounding rule. Missing cost basis means target price unavailable; missing sales means period contribution ranking unavailable. Available partial costs can be displayed as a labeled subtotal, never as complete cost.

Competitor prices, customer price evidence and desired margin are **constraints and comparisons**, not amounts to add together. Show the calculated price beside reviewed comparable ranges and customer evidence. If the cost/margin target exceeds supported customer prices, flag the conflict and show transparent alternatives for owner review (cost, portion, channel, product mix or target). Do not claim a profitable demand level without a supported demand model or experiment.

## Key-item and operation criteria

Provide separate sortable measures rather than a single unexplained score: unit contribution, total period contribution, sales mix/volume, cost exposure, confirmed waste cost and contribution per constrained-resource minute. Keep negative/undefined values visible. A high-margin low-volume item and a low-margin high-volume item may rank differently. Define any high/low thresholds per business and period; an ABC/menu category cannot be asserted from missing demand data. Strategic owner labels remain separate from measured financial results.

## Delivery and acceptance

1. Implement pure typed cost/scenario functions with synthetic, independently worked expected values before introducing storage or routes.
2. Add reviewed cost/market/assumption history and a shared selection service once C16 source/definition selection is accepted. Verify hashes, same-business references, roles, concurrent approvals and unchanged receipts.
3. Expose bounded business detail and portfolio preview data; include scenario status, key figures and drill-down references without overloading the existing five KPI contract. Advisor prose uses only the selected typed facts.
4. Build the minimal Persian dashboard sections after backend gates and verify evidence navigation, missing/stale/conflict states, decimal/toman display, RTL and accessibility. Pricing never bypasses the forty-day plan's feature freeze or pilot dependencies; richer demand optimization remains later work.

Required arithmetic cases include: normal gross-versus-net recipe yield, packaging by channel, zero versus missing costs, normal loss counted once, separate abnormal loss, batch output, shared-cost conservation, margin versus markup, percentage and fixed/order fees, invalid denominators, exact IRR/toman conversion, rounded-price margin, stale/conflicting sources, negative contribution, mixed sales prices, zero volume/time and direct resale. Integration must cover corrected recipe/cost histories, unresolved packs, immutable earlier results, source tampering, tenant isolation and reviewed customer/competitor observations. No customer profitability or pricing effectiveness is claimed until permissioned pilot data and owner decisions/outcomes are evaluated.

## Research basis and limits

The [SBA's break-even explanation](https://www.sba.gov/counseling/plan-your-business/) separates fixed costs, variable costs and contribution. Use it for scenario terminology, not proof of actual demand or a single-product break-even rule for an unknown product mix. XRB's officially published [NZ IAS 2, paragraphs 11–16](https://standards.xrb.govt.nz/standards-navigator/nz-ias-2/) distinguishes acquisition/conversion costs, systematic production overhead allocation and abnormal waste. This is a primary source for the New Zealand equivalent standard, informing the separation of managerial pricing from inventory valuation; it does not establish current Iranian accounting compliance or a default valuation policy for Herman. The IFRS Foundation's 2021 IAS 2 PDF appeared in search excerpts but direct opening redirected to a subscription page; no unrestricted full-text access is claimed.
