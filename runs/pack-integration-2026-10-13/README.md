# C16 pack timeline integration — 2026-10-13

Status: analysis/duplicate/freshness integration implemented; remaining C16 gates stay open.

## Behavior

New inventory analysis selects all eligible pack definitions in the same database snapshot as its inventory inputs. The flat input receipt adds `pack_definitions`; the existing baseline `conversions` remain source evidence but are never used as a fallback by the dated calculator. Migration 16 adds immutable `pack_uses` to analysis receipts without rewriting earlier snapshots or input hashes. Each selected factor retains record/item/time, definition ID, exact quantities and source.

Freshness validates the saved hash first and compares typed definitions alongside existing inputs. A legacy receipt without the new field is interpreted using baseline definitions from its own saved conversion rows. New revisions can conservatively make a previous analysis stale, including future revisions; this does not assert that its historical arithmetic changed. Stale results and pack-use details are withheld from new advisor context. Prior analysis rows and saved case turns stay immutable.

Duplicate candidates now normalize pack quantities with the unique factor valid at the shared item/event instant. The duplicate workflow still proposes candidates for human disposition; equal quantities alone do not establish duplicate events. A neutral pack selection module prevents service/selector import cycles.

## Validation

The related freshness/duplicate/integration suite passed **42 tests in 129.97 seconds**. After adding advisor pack-use context and historical case checks, the focused integration suite passed **two tests in 12.42 seconds**. The independent example changes a newly calculated shortage from 64 to 58 units when a future eight-to-ten-unit pack revision covers part of the period, while the old receipt remains 64. A copied legacy-shaped receipt is current before the revision and stale afterward; new case context suppresses stale figures, and the first case receipt stays unchanged. Duplicate checks match eight units before activation and ten after it.

Initial focused failures were test adaptations: exact decimal serialization preserved trailing zeros, so numerical expectations now compare Decimal values; the read-without-recalculation test now patches the actual dated calculator entry point. Neither change weakens the assertions about arithmetic or read behavior.

Full Windows PostgreSQL regression: **398 passed, one real-OCR skip, 69 warnings in 488.74 seconds**. Existing dependency/serialization and temporary-cleanup warnings remain; no real OCR/model-quality claim follows.

Code commit `16c4f3cb681ec88e9fa2181b81dfce9b6a1a1f43` passed [Linux CI](https://github.com/alisunkazemi21-cloud/Herman-SME-Financial-Advisor-Perisan/actions/runs/38363836437); **397 passed, two skipped, five warnings in 78.16 seconds**. Ruff passed. Marimo exited successfully with host configuration-access warnings; the user-deferred notebook is unchanged. Graphify code-only extraction/report completed with 1,353 nodes, 4,370 relationships and 86 communities; token savings remain unmeasured.

## Remaining gates and user steering

Historical inventory-row bindings, item name/SKU revision lifecycle, public revision routes and their end-to-end acceptance remain unfinished; this is not complete C16. Real documents/model quality, recovery/capacity and owner UI remain open. The user's operational-risk brief is captured in `research/PILOT_DELIVERY.md`: weekly reconciliation for data-ready businesses, category-level completeness, named responsibility, reviewed action/outcome, real renewal and setup/recurring support-cost measurement. These are planning and acceptance requirements, not delivered pilot telemetry or customer results.
