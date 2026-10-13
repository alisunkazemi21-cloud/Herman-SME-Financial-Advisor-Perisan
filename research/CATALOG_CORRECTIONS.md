# Catalog and unit-definition corrections — C16 design contract

Status: **in progress**, 2026-10-13. The event-time calculator and internal pack persistence/review are implemented; the complete reviewed catalog workflow is not yet accepted. The baseline remains C15 plus the POSIX cleanup repair at commit `1589a7e`. See the [progress map](PROGRESS.md) and [validation record](VALIDATION.md).

## Problem and current boundary

An owner can discover that an item name or SKU is wrong, or that a pack contains a different quantity from the currently recorded conversion. The current `items` and `unit_conversions` rows are insert-only. Replacing their values in place would change the meaning of earlier stock counts, movements, recipe lines and saved analyses. The current calculator receives one catalog and conversion set for the whole request; it does not select definitions by event time. `unit_conversions` permits one `pack` factor per item. Any new definition must therefore change the selection and calculator contract, not merely add an edit endpoint.

`g`, `ml` and `each` represent different physical dimensions. The current schema has no safe general conversion between them. A correction from one of these base units to another cannot silently keep the same item identity or reinterpret existing quantities.

## Decision for implementation

Keep a stable item identity for a physical item whose base unit and direct/recipe meaning remain unchanged. Add immutable, reviewed catalog revisions for display name and SKU aliases, and immutable, reviewed pack-factor revisions with a prospective effective instant. The existing rows form the baseline revision when migration 15 is applied; migration must not invent a human approval of their historical values. A new revision is proposed with source evidence, reviewed by an owner or reviewer, and becomes selectable only after approval. Rejection leaves the current definition unchanged. A revised factor never changes a prior revision row.

For a mistaken base unit or a change between direct material and recipe product, create a separate item identity and require an explicit stock handover/count under the existing reviewed-record workflow. The system must show both histories and the boundary. This is an operational correction, not an implicit unit conversion. A subsequent checkpoint may add a reviewed cross-identity migration workflow if pilots establish a need.

Alternatives considered:

| Option | Consequence | Decision |
|---|---|---|
| Update a catalog or conversion row in place | Earlier quantities and receipts could acquire new meaning. | Reject. |
| Create an unrelated item for every spelling or pack-factor change | Preserves history but fragments one physical item's stock across identities. | Reject for compatible edits. |
| Add reviewed definition revisions with effective instants | Keeps one physical identity and exposes the applied definition. Requires time-aware calculation and migration. | Choose for names, aliases and pack factors. |
| Convert between `g`, `ml` and `each` automatically | No general physical conversion exists. | Reject; use a new identity and an explicit handover. |

## Identity, time and review

- Item ID remains the stable key for a compatible item. Existing stock and recipe foreign keys do not change. The baseline base unit and consumption mode remain immutable.
- Each proposed revision has its own ID, same-business item ID, predecessor ID, kind, typed replacement value, source document and locator, author, creation time and decision history. Version-specific name/SKU and factor values are immutable after proposal. Database constraints and triggers must prevent late detail or source injection.
- Approval is an owner/reviewer decision with a reason. The approval transaction chooses a server-authored `effective_at` at or after approval time; optional future activation is allowed. Backdating a revised factor through catalog approval is forbidden. A historical error requires review of the affected stock/recipe records and explicit C13 corrections where necessary.
- At most one approved successor can replace a given live definition. Competing pending candidates do not affect calculations. Rejected candidates do not consume the successor slot. Version chains remain visible and bounded.
- A SKU change retires the old active alias at activation. Active aliases are unique within a business. Historical rows and receipts retain the alias used at their creation. Reusing an old alias for another item requires an explicit conflict check, never a silent remap during import.
- All definitions and evidence are scoped to the business. The runtime database role must retain no update/delete path for catalog values or decisions. Idempotent retry returns the same original result; a changed request cannot reuse the same key.

## Calculation and historical meaning

The calculator must resolve a pack factor for each quantity at that quantity's event instant, and capture the selected definition ID and factor in the new analysis input receipt. Stock counts use count time, movements use movement time, fulfilled products use fulfillment time, and recipe ingredients use the fulfillment time under the recipe version selected at that time. A pure calculation request must either include a complete definition timeline or explicit binding per input; one current factor for a multi-period request is insufficient.

Gregorian instants remain the database comparison basis; Jalali dates are display/input conversions with explicit timezone handling. Intervals are half-open. When no unique reviewed definition covers an input, analysis is incomplete with the missing definition named. The calculator must not choose the latest factor when the event predates it. Amounts and factors remain exact decimal strings. A valid result still uses the existing `g`/`ml`/`each` canonical base, so a revised pack factor can change future converted quantities without changing the unit dimension.

Saved analysis receipts and case turns stay immutable. A later revision may make a selected analysis stale or unknown under the current freshness contract; it never rewrites the saved figures. The new receipt must identify applied revision IDs and source locations. New context suppresses stale figures until a reviewed new analysis is created. A display-name correction may conservatively mark a receipt stale even if the arithmetic is equal; freshness must state that it is a changed input, not infer a changed shortage.

Existing records at migration time must bind to the baseline definitions they used. The migration may derive this binding from their stored item/unit values and the single existing conversion per item; incompatible or ambiguous legacy rows must be flagged for manual review rather than assigned a guessed factor. The migration must preserve old analysis hashes, result strings and references exactly. A default analysis spanning pre- and post-activation quantities must be independently checked against the captured timeline.

## Proposed API and acceptance gates

The exact route names and tables will be fixed after migration design, before implementation. Expected operations are: propose a typed item/alias or pack-factor revision, list current and historical definitions, review or reject a proposal, and inspect its evidence and successor chain. List/detail reads use `no-store`; write routes require authentication, same-business access and idempotency. No model output may propose an approved definition or decide one.

Acceptance requires independent examples for: a name/SKU typo, 1 pack = 8 units becoming 10 prospectively, an analysis crossing the activation time, a backdated record, ambiguous/missing factor, concurrent approvals, rejected proposals, tenant/role enforcement, source tampering, duplicate alias conflicts, unchanged historical receipts and case turns, freshness behavior, migration reentry and safe handling of legacy ambiguity. Check database invariants directly as well as API responses. A Windows local regression and Linux CI must pass; real customer data, OCR and model quality remain separate gates.

## Implementation order

1. Freeze the baseline and define revision/binding schema plus migration-reentry behavior.
2. Implement typed proposals and database-enforced human review, including SKU alias uniqueness and source sealing.
3. Add time-aware definition selection and a pure calculator contract; carry selected revision IDs into new receipts.
4. Connect database analysis and freshness selection, then list/detail and API routes.
5. Validate the independent arithmetic, concurrency, access and historical cases; synchronize run README, decision log, progress map, report, research chapter and media narrative before publication.

This contract does not assert that catalog corrections, changing unit dimensions, 1,000-business workload capacity or the deferred owner interface are complete.

## Implemented calculation slice

`src/backend/dated_inventory.py` introduces a separate `DatedInventoryRequest` envelope and `DatedInventoryResult`, leaving the legacy request/result serialization unchanged. It invokes the existing reconciliation arithmetic with an internal pack resolver. `PackDefinition` distinguishes migration baseline values from approved, proposed and rejected definitions. Baselines have no invented approval; new approved definitions cannot start before their approval instant. The internal database timeline now supplies approved definitions; public analysis integration still remains. Client assertions are not approval authority. This module is not exposed through an API.

Counts and movements resolve at their own instants; fulfillment quantities, recipe output packs and ingredient packs resolve at fulfillment time. Only a unique eligible half-open interval can produce a number. Receipts capture record/item/ingredient IDs, time, definition ID, exact factor, input quantity, converted quantity and source. A failed calculation returns no partial pack-use receipt. Pending/rejected candidates cannot displace approved values.

Intervals in this calculation envelope are selected snapshots: the database adapter must derive each end from its approved successor, never update an immutable definition row to close it. This establishes the arithmetic before migration 15. The following persistence slice now stores and reviews pack revisions. Historical inventory-row bindings, aliases, duplicate matching and freshness integration remain open. Analysis integration is now implemented as described below; public revision routes remain gated. See [slice evidence](../runs/dated-inventory-2026-10-13/README.md).

## Implemented pack persistence slice

Migration 15 adds `pack_definitions` and `pack_decisions`. Existing conversions are copied exactly into baseline rows with the same IDs and no invented reviewer or approval. Future conversion inserts capture baselines atomically. Typed proposals store factor and source together; decisions derive predecessor identity, use server decision time and enforce prospective, strictly ordered activation. Unique approved-successor slots arbitrate concurrent reviews; rejection leaves the slot available. Forced RLS, author/reviewer policies and append-only triggers protect storage.

`Catalog` is an internal service using the existing idempotency and audit transaction. Proposal and approval verify source file hashes; rejection remains possible when the source is unavailable. History is paginated and the timeline derives end instants from approved successor decisions. No public revision route is added. Analysis now consumes the dated timeline through the integration below. Migration 15 establishes definition baselines only; historical per-record bindings require a later migration, preserving existing receipts.

The initial persistence suite passed nine PostgreSQL tests, including an isolated database upgraded from migrations 1–14 and migrated twice without changing its legacy conversion. Full regression and publication evidence are recorded in [the persistence run](../runs/pack-catalog-2026-10-13/README.md). C16 remains in progress.

## Implemented analysis integration

Inventory selection now includes the bounded reviewed pack timeline in the same transaction. New flat snapshots add `pack_definitions`; migration 16 adds the immutable `pack_uses` analysis column. The calculator receives no static conversion fallback. Legacy snapshots and hashes remain unchanged; freshness interprets their saved conversions as baseline definitions only for comparison. New advisor context exposes current pack-use receipts and suppresses them with stale figures. Duplicate normalization resolves the event-time factor. [Integration evidence](../runs/pack-integration-2026-10-13/README.md) records arithmetic, legacy comparison and saved-case checks. Historical per-record bindings, item/SKU revisions and public routes remain C16 gates.
