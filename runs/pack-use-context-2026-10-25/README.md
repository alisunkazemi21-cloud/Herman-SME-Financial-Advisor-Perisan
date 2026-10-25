# C16 fulfillment and recipe-path pack-use identity

Date: 2026-10-25. This calculation/receipt slice prepares historical binding; C16 remains open.

## Behavior

The pack resolver carries the originating fulfillment ID and ordered recipe-ID path through recursive expansion. New `inventory.dated_pack.v2` results contain `pack.use.v2` entries. Direct stock counts/movements have no fulfillment context, direct fulfillment quantities name their own fulfillment, and recipe output/ingredient uses name their originating fulfillment and complete recipe path. Ingredient identity distinguishes output from line consumption. The same shared recipe reached through different branches no longer creates an ambiguous use key, even for separate orders at the same instant.

Versioned validation rejects contradictory path/record/fulfillment metadata and mixed-version aggregates. Old v1 receipts parse with unknown ancestry rather than invented context. The legacy `InventoryRequest` / `InventoryResult` shapes and exact arithmetic remain intact. No database migration or persisted receipt rewrite occurs.

## Validation

Final focused Windows arithmetic/contract regression: **52 passed in 0.35 seconds**. It covers same-time fulfillments through a shared-subrecipe DAG, output/ingredient/direct use identities, malformed context/version rejection, legacy-v1 parsing, half-open factor selection and unchanged snapshots. The independent expected usage for two orders with two eight-unit branches each is 32.

PostgreSQL analysis/case integration initially passed two tests in 30.86 seconds. After explicitly checking v2 context fields in persisted analysis and saved case receipts, the final focused run passed **two tests, two warnings, in 21.52 seconds**. Saved receipts remain equal after a factor revision; new analysis still changes shortage from 64 to 58 and stale advice withholds previous figures. Independent review found no actionable issue and requested the additional output-pack identity assertions, which passed. Ruff passed.

The preceding alias checkpoint already passed the full Windows suite (418 tests / one skip). For this pure callback/JSON-metadata change, Windows verification is the focused arithmetic and database regression above; full Linux CI passed as recorded below. No new full Windows count is claimed. The notebook is unchanged; its existing validation remains recorded with the alias checkpoint.

Initial context code commit `e392845af163dfa8f05f5d2ed5fa0149ac8b2dfd` failed [Linux CI](https://github.com/alisunkazemi21-cloud/Herman-SME-Financial-Advisor-Perisan/actions/runs/40144776515): one alias-exclusion deadlock failure, 422 passes, two skips and 15 warnings in 77.70 seconds. The new arithmetic/context tests passed within that run; the preexisting concurrent-alias test exposed incomplete application deadlock recovery. A follow-up repair adds complete atomic retry, bounded conflict handling and explicit rollback/idempotency/concurrency tests. The repair passed **20 PostgreSQL alias/import/backend tests**, two warnings, **98.50 seconds**, including bounded retry exhaustion and recovery. Independent review confirmed the retry exits/rolls back the failed transaction before starting a fresh attempt. Repair commit `d6270a2b136404a14013b953612b988b7cca6e5e` passed [full Linux CI](https://github.com/alisunkazemi21-cloud/Herman-SME-Financial-Advisor-Perisan/actions/runs/40145114933): **426 passed, two skipped, 15 warnings in 82.14 seconds**, followed by Ruff and Marimo. Graphify code-only refresh/report completed with **1,442 nodes, 4,635 relationships and 85 communities**; token savings are unmeasured. The receipt-identity and bounded retry slices are verified within this scope; complete C16 and broader release gates remain open.

## Remaining gates

Persistent historical checks/resolutions, known-before-event baseline provenance, current label integration and public revision routes remain unfinished. Future proposals must still select prospective factors dynamically; recipes must bind at fulfillment time. This slice provides identity only. Real-document/model, recovery, complete workload capacity and pilot evidence remain separate release gates.
