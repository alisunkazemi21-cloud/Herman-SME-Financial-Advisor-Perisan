# Catalog and unit-definition corrections — C16 design contract

Status: **accepted for compatible catalog edits**, October 26, 2026. Code `f877b9b` passed 544 Windows tests / one real-OCR skip and 543 Linux tests / two skips, plus Ruff/Marimo. See the [acceptance matrix](../runs/catalog-workflow-2026-10-26/README.md#acceptance-mapping) and [public API guide](CATALOG_API.md). The dated design/implementation sections below retain their historical context; the latest section records final acceptance.

## Original design problem and correction boundary

An owner can discover that an item name or SKU is wrong, or that a pack contains a different quantity from the currently recorded conversion. At the original design baseline, `items` and `unit_conversions` rows were insert-only. Replacing their values in place would change the meaning of earlier stock counts, movements, recipe lines and saved analyses. The original calculator received one fixed catalog/conversion set; the accepted implementation below now supplies dated selection. `unit_conversions` permits one `pack` factor per item. Any new definition must therefore change the selection and calculator contract, not merely add an edit endpoint.

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

The initial persistence suite passed nine PostgreSQL tests, including an isolated database upgraded from migrations 1–14 and migrated twice without changing its legacy conversion. Full regression and publication evidence are recorded in [the persistence run](../runs/pack-catalog-2026-10-13/README.md). At that October 13 slice, C16 remained in progress; final acceptance is recorded above and in the October 26 section.

## Implemented analysis integration

Inventory selection now includes the bounded reviewed pack timeline in the same transaction. New flat snapshots add `pack_definitions`; migration 16 adds the immutable `pack_uses` analysis column. The calculator receives no static conversion fallback. Legacy snapshots and hashes remain unchanged; freshness interprets their saved conversions as baseline definitions only for comparison. New advisor context exposes current pack-use receipts and suppresses them with stale figures. Duplicate normalization resolves the event-time factor. [Integration evidence](../runs/pack-integration-2026-10-13/README.md) records arithmetic, legacy comparison and saved-case checks. Historical per-record bindings, item/SKU revisions and public routes remain C16 gates.

## Historical-binding design findings — 2026-10-25

Source review identified two compatibility requirements for the remaining per-use pack-binding work. Future-dated proposals cannot freeze a concrete factor permanently at creation: the accepted event-time integration example creates future records first, then approves a prospective factor and expects a new analysis to change while the saved receipt stays immutable. Distinguish historical-event capture from deferred future selection. Recipe ingredients and output packs resolve at fulfillment time, never once at recipe creation.

At that review, the v1 analysis-local `PackUse` carried a recipe record ID and ingredient ID but no fulfillment ID. Separate fulfillments at the same instant can therefore have indistinguishable persistent usage keys. Add fulfillment context (and nested recipe path where required) before imposing unique persistent recipe-use bindings; existing ordered analysis receipts remain valid historical snapshots. Legacy conversions have no creation timestamp, so a migrated baseline association is derived interpretation, not proof that the factor existed when the record was entered. Missing/ambiguous interpretations need explicit review, and analysis/duplicate normalization must consume the same resolved binding. This is design evidence, not implemented binding storage.

## Implemented dated item-alias slice — 2026-10-25

Migration 17 captures baseline item labels with the original item ID and adds immutable `item_definitions` / `item_decisions`. Baselines have no invented source/reviewer. Proposals retain source and author; prospective human decisions publish a half-open SKU interval. A `btree_gist` exclusion rejects overlapping same-business/SKU periods, including future/concurrent claims. A trigger-maintained `item_alias_periods` projection closes predecessor intervals atomically; runtime access is SELECT only, with scoped security-definer maintenance, fixed search path, forced RLS and revoked public function execution. Source definitions/decisions remain append-only.

`Catalog.propose_item`, `decide_item` and paginated `item_history` are internal services. The importer parses the row's aware event timestamp before resolving its exact trimmed SKU. Original source values are retained; each new import source captures `item_definition_id`. The database checks that non-null pointers match the concrete record item and event-time interval at insertion. Existing source rows retain NULL (uncaptured), never guessed backfills. A captured pointer records the import's resolution at that time and remains immutable if a later future revision changes selection for a future event. Direct item-ID references stay stable.

The existing importer already trims column text; this adds no fuzzy/case normalization. Original SKUs remain reserved on new identity creation; an alias can be reused on another existing identity only through a reviewed nonoverlapping revision. Name-only changes use the same lineage. Base units and consumption modes remain unchanged.

Operational dependency: PostgreSQL must provide `btree_gist`; migration installs it in `public` through the migration connection. Readiness now probes alias/source features as well as pack features. The synthetic benchmark's item setup now selects tenant context for baseline publication; the million-row benchmark was not rerun in this checkpoint. Existing benchmark results remain historical evidence only.

Focused evidence: nine direct-storage/source-guard tests passed, including fresh pre-17 upgrade/reentry, concurrent collision, half-open boundaries, retired-alias reuse, role/RLS, baseline forgery and projection mutation guards. Forty importer/correction tests passed, preserving original source receipts across activation and rejecting retired SKU imports atomically. Independent review found no remaining actionable issue in this scope. Full regression and code-commit CI evidence are maintained in the [run record](../runs/item-aliases-2026-10-25/README.md).

C16 is still open: historical pack-use bindings, current catalog/display-label integration and public revision routes remain to finish. Existing item lists and analysis item labels still use the original immutable item rows; this slice must not be described as a complete visible catalog-editing workflow.

### Binding implementation direction, still pending

The exceptional historical risk is a newly available baseline with an unbounded start: it can turn a previously unsupported past use into a number. Prospective approved successors cannot backdate that change. Plan append-only historical-use checks, explicit unresolved states and separate reviewed resolution decisions, with one approved resolution and correction by a new inventory record if that resolution was wrong. Migration-derived unique associations preserve an existing interpretation without claiming original operational truth. Future uses stay deferred; a later write analysis/review can capture them after their event becomes past, while read-only freshness/duplicate queries never create bindings. Analysis and duplicate normalization must share resolution and refuse unsupported matches.

Do not treat a migrated baseline's `created_at` as its original operational creation time. If a later implementation uses known-before-event eligibility, distinguish a trusted observed/captured timestamp from that legacy creation claim; an explicit migration observation time can prove presence from that observation onward, without inventing an earlier origin. The final schema must make this distinction visible. New receipts/freshness comparisons will include selected binding/resolution identities, preserving all earlier snapshots/hashes/results. Acceptance must retain the existing future-event 64-to-58 calculation example, require review after late/missing baseline data, resolve recipe uses at fulfillment time, and test concurrent resolution, tenant/role/source integrity and duplicate consistency.

## Implemented pack-use context identity — 2026-10-25

The pure calculator now emits `inventory.dated_pack.v2` envelopes and `pack.use.v2` entries with originating fulfillment ID and an ordered recipe-ID path. Output versus ingredient remains distinguished by a null versus concrete ingredient ID. Shared nested recipes reached by different branches and separate orders at one timestamp now have distinct use keys. Direct counts/movements have no fulfillment/path; direct fulfillment quantities identify their own fulfillment. No arithmetic, base-unit rule or existing inventory-result shape changes.

Legacy v1 entries parse with unknown fulfillment context; old ancestry is never fabricated. Aggregate version checks reject mixed v1/v2 entries, and v2 validates path/record/fulfillment consistency. Existing database JSON receipts are not rewritten. The extra identity prepares persistent recipe-use binding but does not implement it or approve a historical factor. [Verification](../runs/pack-use-context-2026-10-25/README.md) includes arithmetic, nested shared paths, equal-time fulfillments, explicit v1 parsing, saved-case receipts and unchanged prospective-factor behavior.

## Historical binding storage and review — 2026-10-25

Migration 18 implements the observation/cutover, server-stamped legacy-source flag, immutable per-use checks and separate review decisions. A legacy source uses the stable flag, not transaction-ID ordering. Existing past direct pack rows are backfilled; new past direct details capture atomically, and recipe checks accept their concrete fulfillment/path context. Future uses are deferred. Guarded origin/state fields distinguish supported, migration-derived and unresolved interpretations. Only owners/reviewers can approve a source-backed eligible resolution; rejections retain history and leave the approval slot available. Approval verifies relevant source bytes through the internal service.

The final affected PostgreSQL regression passed 68 tests, including upgrade/reentry receipt preservation, cutover concurrency, canonical path bounds and reviewed-resolution races. [Evidence and publication limits](../runs/pack-bindings-2026-10-25/README.md): code is committed locally; full CI/publication remain pending after automatic permission-review timeouts. Analysis/freshness/duplicate consumers are not yet binding-aware. The following slice must connect all three consistently and preserve the existing future-event 64-to-58 behavior, rather than describing storage as completed live-analysis protection. No public revision routes are added.

## Shared historical interpreter — 2026-10-25

`pack_interpretation.py` supplies the pure binding-aware selection and arithmetic contract. Its server snapshot includes observations, cutover/as-of times, legacy flags, checks and approved resolutions. Existing unresolved checks are sticky, bound checks retain their identity, explicit resolutions retain evidence, and future selections stay dynamic. The new bound envelope/v3 uses coexist with unchanged dated v1/v2 tools. Exact provenance, chronology, multiplication and evidence checks are enforced. A bounded nonnumeric encountered-context trace supports later batch capture on writes without source traversal duplication or numeric receipts on failure. [Verification](../runs/pack-interpreter-2026-10-25/README.md): 99 related tests and independent review; live database wiring remains pending.

The next adapter must select observations for supplied definitions, legacy flags for selected source IDs, checks by exact usage/root fulfillment and approved resolutions for those checks. Count metadata against the same global row/byte budgets as other inventory inputs. Keep original source values; include final normalized interpretation IDs/version in new input snapshots before hashing. Source hashes for selected resolution evidence must be verified by analysis writes. Capture only encountered past uses on authorized transactions; readers must not write. Use batch capture/reload, retaining server chronology and handling an event crossing from future to past during a write explicitly.

Freshness indexes stable metadata and approved resolutions, excluding clock passage itself. Old pack receipts with insufficient historical context require unknown, while independently provable no-pack comparisons can remain current. Duplicate normalization must resolve each record independently and skip comparison if either side is unavailable; comparing two unavailable values or raw unresolved packs would retain the current defect. Service, adapter, freshness and duplicates need joint PostgreSQL acceptance before public catalog routes open.

## Live historical binding consumers — October 26, 2026

Code `3328736` connects the shared interpreter to all three live consumers. The selector loads metadata in a scoped snapshot within the shared row budget. Analysis batch-captures encountered past context keys, reloads metadata, verifies original/definition/resolution-only source bytes and hashes final check/review IDs before storing results. A future-to-past crossing with an uncaptured context rejects the write. Failures roll back capture and analysis together. Reads never capture.

Freshness indexes stable version/cutover/legacy/observation/check/review content, excluding as-of clock passage. Unsupported legacy pack context is unknown; approved resolutions make prior current context stale, while saved receipts remain exact. Numeric duplicate candidates independently normalize each record and skip any unavailable side, including two unavailable values. Complete-comparison row/read-byte and final-envelope byte limits fail explicitly and cannot become partial approval permission.

Full exact-code Linux CI passed 513 tests / two skips, plus Ruff and Marimo. The full Windows run passed **514 tests / one real-OCR skip / five warnings / 862.56 seconds**. Source review found and verified repairs to the unbounded helper metadata callback and final encoded-envelope overhead. [Run evidence](../runs/binding-consumers-2026-10-25/README.md). Current item-label presentation and reviewed public catalog/binding workflows are the next C16 work; public revision endpoints remain gated until their acceptance.

## Current labels and public workflow — October 26, 2026

Code `f877b9b` implements the remaining current-label and reviewed public workflow. `catalog.item_labels.v1` selects one published label per stable item at the reporting end, validates exact identity/text/instant agreement, joins the existing input budgets/hash and verifies selected revision evidence. Freshness compares selected label meaning and excludes only an off-scope derived interval-end change; legacy snapshots compare their recorded text without fabricated old definition IDs. Original items, dimensions/modes and source/import/analysis/case history remain unchanged.

The [public API guide](CATALOG_API.md) fixes route names, roles, pagination, exact decimals, no-store/redacted handled errors and the catalog-versus-historical-use distinction. Manual captures use a source-key conflict clause with the existing bounded transaction retry. Public acceptance includes competing item/pack decisions, simultaneous recipe captures, explicit past-use resolution, alias conflict rollback, no backdated activation and selected-label-only evidence tampering.

Lead scoped runs passed 51 joint and four final cases. Exact-code Linux CI passed 543 tests / two skips, Ruff and Marimo. Full Windows regression passed 544 tests / one real-OCR skip / five warnings in 777.37 seconds. [Acceptance matrix and synchronized evidence](../runs/catalog-workflow-2026-10-26/README.md). C16 is accepted within this compatible-edit backend contract; broader product and pilot gates remain separate.
