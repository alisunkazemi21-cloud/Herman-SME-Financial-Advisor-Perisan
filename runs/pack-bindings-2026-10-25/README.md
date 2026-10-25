# C16 historical pack-binding storage and review

Date: October 25, 2026. Code commit: `f41c8fbbee0a15b6574b4eb6473c223d962a881c`. **Locally validated storage slice; GitHub publication/full CI pending. C16 remains open.**

## Delivered behavior

Migration 18 records definition observation times, a trusted cutover and stable legacy-source flags. It backfills checks for existing past direct pack quantities without changing original quantities or saved analysis inputs, results, hashes or pack-use receipts. Existing baseline interpretations are explicitly migration-derived; approved eligible successors are known-before-event. Newly inserted backdated sources cannot forge legacy status. Future quantities remain deferred.

Immutable checks identify concrete direct or recipe/fulfillment/path uses. Database guards derive the item, event time and bound/unresolved state. Missing or late baselines leave an unresolved check; inserting a later definition never changes that check. Owner/reviewer decisions can approve an event-eligible interpretation with evidence, while rejection leaves the approval slot available. Source/check/decision history remains append-only, tenant-scoped and protected by forced RLS. Internal `PackBindings` supports idempotent capture, reviewed resolution and bounded history. Approval verifies original source, recipe-ancestor, definition and review file hashes. Rejection remains available when files are unavailable or changed.

The stable legacy flag survives a logical copy without depending on the destination transaction-ID sequence. This is a design property, not a passed restore drill: the separate pre-existing transaction-based detail-sealing mechanism still requires restore acceptance. Native metadata writes and cutover boundaries are server controlled.

**Analysis, freshness and duplicate matching do not yet consume these checks/reviews.** Public revision routes remain gated. Live calculations continue using their previous dated timeline behavior until the shared binding resolver is implemented and verified. This slice cannot be advertised as complete protection against a late baseline changing live analysis.

## Validation and review

Independent storage review identified three issues, all repaired before the final run: shifted PostgreSQL array bounds could encode a duplicate semantic recipe path; approved-successor backfill needed known-before-event provenance rather than a migration-derived label; cutover time needed capture after the source/definition lock barrier. Tests now exercise each invariant, including a deterministic concurrent pre-cutover writer.

- Combined binding storage/service/catalog regression: **22 passed, two warnings, 56.82 seconds** before the final receipt-preservation assertion.
- Final affected Windows PostgreSQL regression: **68 passed, two warnings, 293.10 seconds**. Modules: `test_pack_binding_storage`, `test_pack_bindings`, `test_catalog`, `test_backend`, `test_pack_integration`, `test_inventory_corrections`, `test_tabular_imports`. This includes a fresh migrations 1–17 → 18 upgrade, reentry, cutover barrier, source quantities and stored legacy JSON representations/hash/pack uses unchanged, recipe topology/canonical arrays, concurrent resolution, source tampering and tenant/role checks. The unsupported legacy receipt fixture tests preservation, not its financial validity.
- Readiness unit checks after adding the new feature probes: **eight passed, one PostgreSQL case deselected, one warning, 4.55 seconds**. The restricted-role readiness test was not rerun locally: automatic permission review timed out twice before execution. Full CI must cover it.
- Ruff and `git diff --check` passed. Marimo check exited zero with existing inaccessible user-config warnings; the notebook is unchanged because this is backend storage and planned dashboard scope only.
- Graphify code-only extraction and cluster report: **1,503 nodes, 4,843 relationships, 88 communities**. Generated files remain local; no semantic/model extraction or measured token-saving claim.

The resumed targeted test initially failed at database setup because the local test server was stopped. Startup recovered the interrupted cluster; its log confirmed readiness before the successful regression. No schema reset was used. An initial regression command named a nonexistent import test file; the corrected module list above completed successfully. These attempts are not passing evidence.

## Publication status and next gate

The local code commit is complete. Shell pushes outside the sandbox were not executed because automatic permission review timed out; the sandbox fallback could not connect to GitHub. Read-only GitHub connector access worked, but its first blob upload also timed out at automatic permission review. No review branch or pull request was created, and no new CI result is claimed. Remote publication must be rechecked from actual repository state before retrying. Preserve the existing local commit rather than reconstructing or force-pushing history.

Next: one binding-aware selector shared by new analyses, freshness comparison and duplicate normalization; capture recipe checks only on authorized writes; retain future-event dynamic selection and unchanged earlier receipts. Then current-label and public revision workflow acceptance. Real OCR/model quality, coordinated restore, complete 1,000-business workload and pilot outcomes remain open.

The owner's new pricing request is recorded as a [designed dashboard/backend extension](../../research/PRICING.md), not implemented functionality. It includes costs, market/customer evidence, target margins and product/activity contribution. It does not bypass C16 or release gates.

## Authorized reconnection follow-up

The previously pending restricted-role readiness rerun is now verified. After the user resumed access, the focused readiness/binding suite passed 22 tests, and the full local PostgreSQL suite passed 487 / one real-OCR skip. The missing development-only review-history index was aligned with the unpublished migration, followed by nine readiness passes. GitHub publication/new Linux CI remain unverified. [Exact reconnection evidence and revisions](../pack-interpreter-2026-10-25/README.md#reconnection-and-full-local-regression). Live binding-aware consumers remain open.
