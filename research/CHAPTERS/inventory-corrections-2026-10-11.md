# Corrected inventory inputs with retained evidence

Milestone **C13** in the [development map](../PROGRESS.md) gives approved operational records an explicit revision path. A correction names an approved predecessor and contains a complete typed replacement. Human approval changes which record participates in a new analysis; it does not edit the original or recalculate earlier results.

Pending corrections must not double count an event or make the existing approved version unusable. Independent pending events retain the earlier incomplete-data rule. One approved successor per predecessor prevents concurrent branches. Duplicate review excludes that correction's own event history, while preserving independent matching candidates and source-row reservations.

Whole-record replacement includes event time and recipe validity. A correction outside the requested period removes the original contribution; missing recipe coverage remains explicit. Opening/closing counts require deliberate current-ID selection because a corrected count may refer to a different cutoff or item.

The same review boundary requires structural immutability. A stored recipe header was previously append-only, but that alone did not prevent later ingredient-line insertion. New headers, typed details, recipe lines and import origins are now sealed to one creation transaction and checked before review. Preparation-yield precision is also validated before database rounding can change it.

New analyses retain separate correction ancestry and inherited import origins. Historical values are evidence of the earlier mapping, not silently relabeled corrected extraction. The [contract](../INVENTORY_CORRECTIONS.md) documents this distinction and the bounded receipt. Twenty-six focused checks passed before one added import-origin case; the full PostgreSQL suite passed **277 tests**, including all 27 new correction cases, with **one real-OCR skip**. Ruff and whitespace checks passed; the final record-detail no-store and exact-decimal response adjustments passed two focused API/backend tests in 8.87 seconds. Freshness/impact reporting for earlier analyses, real engines and operational acceptance remain open.
