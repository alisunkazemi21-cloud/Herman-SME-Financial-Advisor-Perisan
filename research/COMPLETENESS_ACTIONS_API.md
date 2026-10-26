# Completeness and action API

Implementation under C17 validation. [Contract](COMPLETENESS_ACTIONS.md) · [Run evidence](../runs/completeness-actions-2026-10-26/README.md).

All paths below are relative to `/businesses/{business}`. Supply a valid Bearer credential; writes also require `Idempotency-Key` (1–200 characters). Actor identity and review times come from the server. Reusing the same key/payload returns the original result; changing the payload conflicts. Responses, including handled errors, use `Cache-Control: no-store`. Client schemas do not accept server decisions, signatures or timestamps.

## Completeness workflow

| Method/path | Input / result |
|---|---|
| GET `/coverage/assessment` | Aware `start`, `end`, `warehouse_id`, optional `basis=service` or `production`. Returns `snapshot`, `complete`, `provisional`, `blockers_fa`. |
| POST `/coverage` | `CoverageProposal`: id, scope, basis, categories, evidence and optional supersedes_id. Editors/owners/reviewers propose. Returns assessment id. |
| GET `/coverage` | UUID cursor `after`, limit 1–100; assessments, next_cursor and evidence_verification. |
| GET `/coverage/{id}` | Immutable assessment, author/time, decision and approved successor id. |
| POST `/coverage/{id}/decision` | `approved` and nonblank `reason_fa`; owner/reviewer only. Returns assessment id. |

`scope` contains business_id, warehouse_id and aware start/end, with start strictly before end. Business must match the path. Categories is a JSON object with exactly these twelve keys:

| Key | Operational records checked |
|---|---|
| opening_count / closing_count | All active counts at the exact period boundaries in this warehouse. The calculator still requires explicit valid target-item count IDs. |
| purchases | Purchase movements. |
| sales | Fulfilled sale events. |
| returns | Supplier and customer returns. |
| transfers | Transfers in and out. |
| waste | Recorded waste. |
| staff_meals | Fulfilled staff events. |
| complimentary | Fulfilled complimentary events. |
| production | Fulfilled production events. |
| other_use | Other-use, service-usage and count-adjustment movements. The calculator's existing restrictions still apply. |
| recipes | Active business recipes overlapping the period and their ingredient lines. |

Each category has `status`, `note_fa` and `evidence` (document_id/locator, or null for missing/incomplete). Status is records_complete, no_events, not_applicable, missing or incomplete. Positive assertions require evidence; counts cannot be no_events, and not_applicable is restricted to recipes without a fulfilled recipe-mode product requiring them. No-event claims conflicting with recorded events do not support a complete result. Any selected pending operational header blocks completeness, including an unfulfilled order that is not counted as an actual sale.

Approval can record an honestly incomplete assessment. It does not turn missing records into zero events. The decision binds to the server dossier at its transaction snapshot. Replacing an approved review requires its current same-scope predecessor ID; rejected/pending proposals do not displace it. New records, approval state or approved corrections change the dataset signature and require renewed review. C16 labels and pack decisions are assessed separately.

New managed inventory analyses always apply this gate. The original three declaration flags are retained in `input_snapshot.coverage_declaration`; the calculator flags in `coverage` are intersected with `coverage_review`. Old persisted analyses are untouched. Legacy snapshots have unknown current completeness. Reviews made before period end are provisional: their raw conditional calculations may be read from the saved receipt, but current advisor, overview and portfolio figures are suppressed. A new post-period human assessment is required; waiting does not upgrade the review.

The dossier caps operational headers plus recipe lines at 10,000 facts, reports unavailable on overflow and charges facts to the shared selection budget. Final analysis snapshots remain bounded to 8 MiB. Completeness SQL has a 15-second per-statement budget while preserving a stricter configured timeout. A cancelled check recovers its savepoint and yields unknown/unavailable; it cannot publish a partial result or poison later context reads.

## Investigation workflow

| Method/path | Input / result |
|---|---|
| POST `/actions` | ActionProposal; returns action id. Editors/owners/reviewers may propose. |
| GET `/actions` | UUID cursor `after`, limit 1–100; proposals with current state/sequence and next_cursor. |
| GET `/actions/{id}` | Proposal and current head state/sequence plus event page (`after_sequence`, limit 1–100). `next_sequence` is the cursor for more history. |
| POST `/actions/{id}/events` | ActionEvent; returns the immutable event id. |

ActionProposal requires id, same-business analysis_id, kind, title_fa, detail_fa, responsible_name_fa, aware follow_up_at and evidence. Optional responsible_user_id must be an active member of this business when proposed. Kinds: investigate, recount, correct_recipe, record_missing, reduce_waste or other. It may reference an incomplete/stale analysis; investigating missing evidence is useful.

ActionEvent requires kind, expected_sequence (zero initially) and reason_fa, with optional evidence/outcome. Use the current head sequence, independently of which history page is displayed. Only one concurrent append at that sequence can commit.

| Event | Allowed prior state | Actor / resulting state |
|---|---|---|
| approve / reject | proposed | Owner/reviewer → approved / rejected. |
| start | approved | Editor/owner/reviewer → in_progress. |
| note | approved or in_progress | Editor/owner/reviewer; state retained. |
| complete | approved or in_progress | Owner/reviewer → completed; outcome and evidence required. |
| cancel | proposed, approved or in_progress | Owner/reviewer → cancelled. |

Completed, rejected and cancelled actions are terminal. Completion outcomes are confirmed, no_change and inconclusive, all human statements with explanations and evidence. No numeric saving or causal claim is inferred. A wrong proposal is cancelled/replaced rather than rewritten. Proposal and approval/completion source hashes are checked on writes; reads label evidence as not rechecked.

401 means absent/invalid credential; 403 means unauthorized role/tenant; 404 means missing scoped resource; 409 means conflicting sequence, review chain, idempotency, evidence or database reference; 422 means invalid input, bounds or unavailable assessment within the time budget. Clients should retain an unsent draft, show the reason and reload the current state before choosing a new action. Do not blindly retry a domain conflict with a new key.

Follow-up dates store responsibility, not an external reminder schedule. These endpoints do not send messages, bill anyone, approve financial postings or change earlier reports. The minimal Persian owner interface is a later checkpoint.
