# Pilot delivery and recurring-value acceptance

Status: planning contract, 2026-10-13. Derived from the user's operational-risk brief. No pilot, renewal, customer outcome or unit-economics result is claimed. This narrows the first validation exercise, not the long-term financial-advisor objective.

## First service and readiness

Start with a weekly reconciliation of a small, agreed list of expensive ingredients for a restaurant or cafe that already has usable POS exports, recipes and routine stock counts. Involve both the owner and the person responsible for bookkeeping/stock records. Choose the ingredient list and first period with them; do not assume all ingredients or all financial workflows are ready.

Before onboarding, record the business, reporting timezone/period, responsible operator and reviewer, supplier/item aliases, unit definitions and dated recipes. Obtain permission for the required records. Check a representative export and a complete trial period. Missing readiness means assisted preparation or deferral, not a falsely complete analysis.

## Risks translated into delivery requirements

| Risk | Delivery requirement | Current evidence / gap |
|---|---|---|
| Incomplete records | Require opening/closing counts, sales/fulfillment, purchases, returns, transfers, waste, staff meals and other use, or an explicit reviewed statement that a category had no events. Display missing categories and withhold unsupported conclusions. | Existing calculation checks counts, approval and declared coverage. Coverage flags are human assertions, not automatic proof that every operational event was recorded. Category-specific completeness review remains to build. |
| Habits disappear during busy periods | Agree a short weekly checklist, named operator/reviewer, due time and missed-period escalation. | Operational routine and adherence tracking are planned; no automatic reminders or attendance claims. |
| Costly onboarding | Reuse explicit mappings, resolve supplier aliases and package sizes, maintain dated recipes and conversions; log setup time by task. | Explicit CSV/XLSX mappings exist. Pack version work is in C16. Mapping reuse UX, supplier aliases and measured onboarding time remain open. |
| Variance interpreted as theft | Separate observed variance from causes. Show source, units, assumptions, missing evidence and plausible alternative explanations; require review before assigning a cause. | Inventory output explicitly avoids inferring fraud. A structured investigation/outcome workflow remains planned. |
| One useful report but no renewal | Link each reporting period to reviewed action, evidence of outcome and later follow-up; measure repeat use and actual paid renewal. | Case history exists. Verified action/outcome and renewal measures are not implemented. |
| Support overwhelms subscription | Separate one-time setup from recurring review/support; measure staff minutes, model/extraction/hosting cost, actual collections and contribution per customer-period. | These delivery-cost measures are planned. Subscription amount and support assumptions are not established economics. |
| Duplicate work with existing tools | Accept existing POS/accountant exports and demonstrate a specific reviewed investigation, without requiring replacement of the system of record. | Explicit imports exist; connector/export diversity and comparative workflow value require pilots. |
| Operational/model failure | Evaluate real documents and model outputs, retain understandable error states, test backup restoration and define support ownership. | Scoped backend tests exist. Real-engine acceptance, restore drills and representative workload capacity remain open. |

## Four pilot questions and the evidence required

1. **Can usable data arrive consistently?** For every agreed reporting period, record due/received times, which categories are missing, who corrected them and whether the period became reviewable. Report reviewable periods / agreed periods, not only successful uploads.
2. **Does the manager take a useful verified action?** Record the discrepancy, source records, proposed explanations, named reviewer, chosen action and follow-up evidence. A detected difference is neither proven theft nor recovered money. Record unresolved/ineffective actions as well as positive results.
3. **Does the owner renew and pay?** Separate free trial, willingness to pay, quoted price, invoice, collected payment, renewal due and actual renewed period. Interview enthusiasm does not count as revenue.
4. **Does support effort fall with repeated use?** Log setup and recurring minutes separately, including corrections, review, interpretation and recovery. Compare later periods against the same customer's early periods. Excluding founder time would hide the core risk.

Proposed observation window: at least four consecutive weekly periods, followed by a real renewal decision when due. This is a proposed pilot design, not a achieved milestone or a guaranteed statistically representative sample. Agree acceptance thresholds and the manual baseline before starting; avoid setting success criteria after seeing results.

## Measurement definitions

- Onboarding hours = all setup/import-mapping/training/correction minutes before the first accepted period / 60. Record role and activity so repetitive work can be targeted.
- Recurring support hours = review, correction, interpretation and operational support minutes for a customer-period / 60; keep setup separate but visible.
- Reviewed task time saved = comparable manual baseline time minus Herman-assisted total time, including input preparation and review. Label estimates and self-reports; do not mix them with observed timings.
- Customer-period service contribution = collected service revenue minus direct recurring labor, processing, hosting allocations and other attributable variable delivery costs. Show cost basis and period; report setup and fixed R&D separately. This is a management measure, not a claim of audited profit.
- Illustrative scenario supplied by the user: 1,000,000 toman revenue minus 6 hours at 200,000 toman/hour leaves -200,000 toman before hosting, sales or development. All three inputs are hypotheses, not observed prices/costs. Store currency explicitly; do not mix rial and toman.

## Continue, change or stop expanding

Expand only when data readiness, repeated reviewed use, real renewal evidence and measured delivery effort jointly support expansion. If the routine repeatedly fails, fix readiness and responsibility before adding features. If support remains high, narrow the supported export/workflow or change setup/service pricing hypotheses and test them. Keep declined/lost pilots and the reason in the denominator. No numeric success threshold is asserted until a pilot baseline and resources are agreed.

The user's references to Toast, Hami, Menuvex and the World Bank are research leads supplied with this brief. They are not independently verified current claims in this contract. Do not reuse market, competitor or macroeconomic claims externally without checking primary sources and dates. Supplier-price comparisons must disclose dates, quantity/unit and currency; forecasts and nominal growth require explicit assumptions rather than treating nominal increases as real improvement.

## Implementation sequencing

Finish C16 historical meaning and catalog review first. Then specify category-level completeness and a minimal reviewed investigation/action record. Add pilot delivery measurements alongside that workflow before broad rollout. The October 24 forty-day plan schedules a minimal owner interface after backend gates; this contract itself adds no interface, monitoring automation, customer outreach or billing action. The maintained progress map must keep these acceptance gates visible.
