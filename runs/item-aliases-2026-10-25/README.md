# C16 dated item aliases and import-definition receipts

Date: 2026-10-25. C16 slice, not complete C16 or pilot release.

## Change and rationale

An immutable physical item identity can now have source-backed, reviewed name/SKU revisions. Migration 17 captures original baselines without fabricated approvals and retains new definitions/decisions. A derived half-open interval projection enforces same-business SKU nonoverlap using `btree_gist`, including concurrent/future claims. The runtime can only read the projection; a tenant-guarded security-definer trigger with fixed search path publishes approved changes. Original items and source/history rows remain immutable.

Tabular import resolves the SKU at each row's explicit aware event time and saves the chosen definition ID with the original extracted values. The new nullable field preserves uncaptured legacy origins; no existing receipts/hashes are rewritten. A database guard rejects a non-null source definition for the wrong item or event instant. A captured import reference stays as its original resolution, including when later prospective changes affect future selection.

## Verification

Nine direct PostgreSQL storage/source tests passed with two warnings in 33.51 seconds. They cover prospective/half-open activation, rejection/ordered future chains, retired alias reuse, concurrent cross-item collision, role/tenant/RLS, immutable source tables, forged baselines, projection write/function privileges, wrong-item/wrong-time source references, and an isolated pre-17 database upgraded twice without changing original item values.

The first seven-test storage pass preceded the source guard. The guard was then added to the unpublished migration and explicitly applied to the already-migrated local disposable test store. The final fresh isolated upgrade test executes the complete amended migration; CI also migrates a fresh database. No shared schema was reset.

The importer/correction regression passed **40 tests**, two warnings, **127.90 seconds**. Before/at activation imports bind different definitions for the same physical item; saved sources retain original aliases and IDs. A retired SKU import fails atomically. Source tampering blocks approval while rejection remains possible. Existing correction/sealed-source behavior remains covered. Independent review found no remaining actionable issue within this slice.

Ruff passed; Marimo exited successfully with existing host configuration-access warnings. Code-only Graphify extraction/report completed with **1,431 nodes, 4,607 relationships and 96 communities**; no model extraction was enabled and token savings are unmeasured.

Code commit: `a5e5b63a15ba84c3891b8fac0209d12c3ddb11a5`. [Exact-code Linux CI](https://github.com/alisunkazemi21-cloud/Herman-SME-Financial-Advisor-Perisan/actions/runs/40142935263) passed **417 tests, two skips, 15 warnings in 76.85 seconds**, followed by Ruff and Marimo. Full Windows PostgreSQL regression passed **418 tests, one real-OCR skip, six warnings in 1,288.51 seconds**. A read-only observation during the slower local run found a PostgreSQL checkpoint wait; this is not a workload-capacity benchmark. This closes the stated alias slice, with wider C16 gates still open.

## Remaining scope and operational notes

PostgreSQL needs `btree_gist`, installed by migration 17 through the migration connection. Readiness probes the newly required alias/source features. Synthetic benchmark setup now scopes item insertion by tenant. The actual setup SQL was verified for two temporary tenant rows and rolled back, producing two baseline projections. The million-row benchmark was not rerun and no new capacity claim is made.

Current item-list and analysis display labels still use original rows. Public revision routes, label-selection integration and historical pack-use binding remain open. Persistent recipe-use bindings need fulfillment context; future-dated proposals cannot be frozen prematurely without violating the existing event-time calculation contract. This checkpoint makes no new pilot, model/OCR, backup/restore or 1,000-business workload acceptance claim.
