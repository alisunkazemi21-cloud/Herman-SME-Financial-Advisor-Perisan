# C17: reviewed completeness and follow-up

Status: accepted within the documented backend scope. Recorded 2026-10-26 before implementation. Full Windows regression: 590 passed / one skip; Linux CI: 590 passed / two skips. [Run evidence and limits](../runs/completeness-actions-2026-10-26/README.md).

## Managed inventory analyses

Every new saved business inventory analysis requires a reviewed completeness assessment for its exact business, warehouse, half-open period and service/production basis. The three request booleans alone cannot establish completeness. Stateless calculation tools retain their explicitly supplied assumptions; they do not certify a business's records.

The twelve categories are opening_count, closing_count, purchases, sales, returns, transfers, waste, staff_meals, complimentary, production, other_use and recipes. A proposal contains exactly one entry for each. Statuses are records_complete, no_events, not_applicable, missing or incomplete. Positive assertions require an immutable document/locator. Counts require recorded evidence; not_applicable is restricted to recipes when no fulfilled recipe-mode product requires them. No-events assertions are explicit human claims, never inferred from an empty table. Missing or incomplete categories may still be reviewed and approved as an honest assessment, but withhold numeric reconciliation.

An assessment proposal and its decision are append-only. An approved replacement must name the approved current predecessor for the same scope. Pending or rejected proposals do not displace an approved assessment. Only owners/reviewers decide; editors may propose. Database guards enforce authorship, tenancy, category shape, chain uniqueness and server review time. Approval does not establish that an assertion is true outside the supplied evidence.

At decision time bind the review to a server-derived bounded signature of active operational records, boundary counts, overlapping recipes and recipe lines, including approval states and correction identities. Subsequent changes require renewed review. Cosmetic labels and pack-definition decisions remain governed separately by C16. Use UTC-normalized facts and deterministic ordering; cap the dossier at 10,000 fact rows before aggregation and return an explicit unavailable state on overflow. Do not accept a client-authored signature. Reject contradictory no-event claims and unreviewed required records as support for a complete result. Verify source file hashes on approval and before saving a supported analysis.

New analysis snapshots retain the original declaration, typed completeness metadata and selected review identity before hashing. The calculator receives the declaration intersected with reviewed completeness. Missing/stale/contradictory evidence yields incomplete output without partial numeric receipts. Existing saved receipts are unchanged; pre-C17 snapshots have unknown operational completeness for current advice. A review made before period end is provisional even if its supplied records are internally complete: raw conditional calculations may be retained, but portfolio/advisor current figures are withheld until a new post-period review. Clock passage alone never promotes a provisional review.

## Investigation actions

An immutable action proposal links to a same-business saved analysis, names a responsible person, records a follow-up instant and describes a proposed investigation or operational step with source evidence. It may reference an incomplete or stale analysis because investigating missing records is useful. A named person is required; a linked user is optional and must be an active member at proposal time.

Append-only sequenced events implement review, start, notes, completion and cancellation. Owners/reviewers approve/reject/complete/cancel; editors may start or add notes after approval. Each event supplies the expected prior sequence to reject lost updates. Completion requires an outcome (confirmed, no_change or inconclusive), an explanation and evidence. Rejections and cancellations retain reasons. No numeric savings, theft accusation or automatic causal conclusion is inferred from a variance or human outcome. A mistaken proposal is cancelled/replaced, never overwritten.

Public reads/writes remain authenticated, tenant scoped, bounded, idempotent on writes and no-store, with sanitized validation failures. Follow-up dates do not send messages or create reminders. This checkpoint adds no outreach, billing, automatic postings or UI.

## Acceptance

Prove missing reviews cannot be bypassed with three true flags; no-event contradictions, changed records, pending approvals, missing evidence and provisional reviews withhold unsupported current figures. Cover source tampering, role/tenant isolation, append-only guards, replacement races, idempotency, old receipt preservation and action transition races. Run targeted PostgreSQL tests, the complete regression suite and CI before acceptance. Synchronize the maintained run, research, reports and progress artifacts. Real pilot outcomes, support economics, OCR/model quality, restore and full workload capacity remain separate open gates.
