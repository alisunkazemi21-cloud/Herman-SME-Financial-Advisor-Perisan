# C16 calculation slice — dated pack definitions

Date: 2026-10-13. Status: internal calculation implementation; complete C16 acceptance remains open.

## Capability and independent example

A pack can contain eight units before an approved activation and ten afterward. Opening 10 old packs is 80 units. Purchases of two old and three new packs add 16 + 30. Sales of one old and one new pack consume 18. A closing count of five new packs is 50. Expected closing is 108; unexplained shortage is 58. The result captures which definition and source converted each quantity.

The separate dated envelope preserves legacy request/result shapes. Counts and movements use their own times; fulfillment and recipe output/ingredient quantities use fulfillment time. Half-open intervals include the activation instant in the new definition. Missing or overlapping eligible factors produce incomplete output without financial results or partial conversion receipts. Pending and rejected candidates do not affect an approved interval. UTC-equivalent instants select the same definition, and a newly supplied backdated event retains the old factor.

## Validation

Focused dated/legacy inventory suite: **46 passed** in 0.37 seconds. Coverage includes cross-activation arithmetic, recipe ingredients and outputs, gap/overlap, pending/rejected candidates, timezone equality, backdated events, wrong dimensions, scoped identities, invalid lifecycle, exact decimals, no mixed static/dated definitions, unchanged legacy serialization and immutable returned snapshots.

Full local PostgreSQL regression: **387 passed, one real-OCR skip, 60 warnings in 402.11 seconds**. The warnings include existing dependency/serialization and pytest temporary-directory cleanup warnings. Code commit `0740d48ba64dbf82bfbb0f1528e58617406222ef` passed [Linux CI](https://github.com/alisunkazemi21-cloud/Herman-SME-Financial-Advisor-Perisan/actions/runs/38317748850): **386 passed, two skipped, five warnings in 46.61 seconds**; Ruff and Marimo also passed. Counts differ for platform-specific checks.

Ruff passed for all source and tests. Marimo check exited successfully, with host configuration-access warnings; the deferred notebook is unchanged. Graphify code-only refresh and clustering completed: 1,294 nodes, 4,133 relationships, 71 communities. These are static navigation artifacts; semantic extraction and token-savings measurements were not performed.

## Failure and recovery record

The first full run started while the local database was unavailable: 213 passed, one skipped, 174 setup errors, 55 warnings in 113.58 seconds. A separate probe confirmed connection timeout. The existing PostgreSQL data directory was started on 127.0.0.1:55432; its crash recovery completed and pg_isready confirmed readiness. Data was not reset. The suite was then rerun against the ready server.

## Remaining gates

No public endpoint or database migration is added by this slice. The dated adapter accepts trusted definitions and does not authorize approval. Next work is migration 15, append-only revision proposals/decisions, baseline record bindings, SKU alias conflict rules, database-enforced roles/concurrency/source integrity, selector/duplicate/freshness integration and persisted historical receipt acceptance. Existing services retain their previous calculator until integration is validated. Real OCR/model quality, representative capacity, recovery drills and owner UI remain separate gates. C15 remains the last fully verified checkpoint.
