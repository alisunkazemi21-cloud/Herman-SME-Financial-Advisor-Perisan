# Catalog and unit-definition corrections — C16 design contract

Status: **design review**, 2026-10-13. This is the next backend checkpoint, not an implemented or accepted capability. The baseline remains C15 plus the POSIX cleanup repair at commit `1589a7e`. See the [progress map](PROGRESS.md) and [validation record](VALIDATION.md).

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
