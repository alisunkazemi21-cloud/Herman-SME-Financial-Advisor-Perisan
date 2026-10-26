# C16 reviewed catalog workflow and current labels

Date: October 26, 2026. Code `f877b9b0ee782caec53bfa3792e7453e94af187f`, published to `main`. **C16 accepted within its compatible catalog-edit backend scope: scoped acceptance, full Windows/Linux regressions and independent review passed. Broader application acceptance remains open.**

## Delivered workflow

Published item labels are selected from the existing half-open alias projection. Current catalog reads default to a server-authored instant or accept an aware `effective_at`. Each request has its own scoped database snapshot; passing the returned instant to the next stable-ID page fixes the effective selection time, not a database snapshot across requests. Raw creation/resource routes and original items remain compatible. Base unit and direct/recipe mode remain immutable for a compatible identity.

Analysis selects label text and definition IDs at `scope.end`, the reporting/closing instant, and stores `catalog.item_labels.v1` before the input hash. Selected nonbaseline source bytes are verified. Label rows consume the shared row and final-byte budgets. A derived interval-end change alone does not invalidate a receipt when the same label remains selected at that fixed instant. Old snapshots lacking label metadata compare actual recorded text against dated current selection without invented old IDs. Existing historical pack interpretation and unknown-context rules remain intact.

Public authenticated routes now support current item list/detail, bounded label/pack history and definition detail, item/pack proposals and human decisions, and historical pack-check capture/list/detail/review/history. Writes require idempotency keys and the existing role/source/tenant guards. Editor may propose/capture; owner/reviewer decides; viewer reads. Compatible revisions cannot modify dimensions or consumption mode. Decimal values are strings; aware instants and half-open intervals remain explicit.

New financial routes redact request-validation echoes and apply no-store to successful and handled-error responses. A pure scoped ASGI send wrapper changes only response-start headers, without buffering parser bodies or adding readiness/cancellation task groups. Catalog pack detail/history explicitly says historical usage has not been evaluated: publication and interval eligibility alone cannot resolve a stored past-use check. Manual captures use source-key conflict handling and bounded transaction retry to reuse one check.

## Acceptance mapping

| C16 requirement | Authoritative implementation/test evidence | State |
|---|---|---|
| Name/SKU typo, current/pending/rejected labels, half-open activation | `test_current_labels` and `test_http_catalog_half_open_labels_history_and_exact_pack_values` | Scoped pass |
| One physical identity; original dimensions/mode/rows unchanged | Immutable storage tests, HTTP extra-field rejection and raw-resource comparison | Scoped pass |
| Pack 8→10, crossing activation and exact arithmetic | Public HTTP revision/analysis test retains independently expected 64→58 shortage and 18-unit usage | Scoped pass |
| Backdated/missing historical factor requires review | `test_http_unknown_past_requires_explicit_evidenced_review`, binding storage/interpreter/consumer tests | Scoped pass |
| No backdated item or factor approval | `test_public_approval_cannot_backdate_a_definition`, database prospective-order tests | Scoped pass |
| Alias collisions and retired-alias reuse | HTTP atomic conflict/slot test; direct `test_alias_reuse_requires_nonoverlapping_reviewed_interval` | Scoped pass |
| Competing human decisions and natural-key capture concurrency | HTTP item/pack races produce one 201/one 409; simultaneous recipe captures reuse one check | Scoped pass |
| Tenant/role/source integrity; idempotent retry | HTTP authority/redaction/foreign-source tests plus restricted SQL/RLS and immutable storage tests | Scoped pass |
| Source tampering and rollback | Separate label-only source, pack/review-source tests, rejected proposal remains reviewable | Scoped pass |
| Earlier analyses, import origin and saved cases unchanged | HTTP analysis/case and dated import tests; existing receipt representation migration tests | Scoped pass |
| Freshness for changed selected labels/reviews, legacy ambiguity | `test_current_labels`, live-binding/freshness tests and public analysis workflow | Scoped pass |
| Migration backfill/reentry and legacy interpretation | Existing pre-15/17/18 isolated upgrade and protected metadata tests, included in full CI | Full regression pass |
| List/detail/history, bounded pages, source/predecessor/successor visibility | HTTP history/detail pagination tests; exact Decimal and no-store/error checks | Scoped pass |
| Windows regression, exact-code Linux checks and artifact synchronization | Exact-code Windows/Linux results below; all five checkpoint outputs synchronized | Passed |

This matrix audits the compatible-edit C16 backend contract. Cross-identity stock handover, a visible owner interface, actual OCR/model quality, complete workload capacity, coordinated restore and pilot/renewal evidence remain outside this accepted scope. Their overall project gates remain open.

## Validation and repairs

- Dated-label worker: new real PostgreSQL suite **15 passed in 53.06 seconds**; 59 prior scoped regression cases also passed. Its first combined run reported **64 passed / ten failed / 249.97 seconds** because new fixtures moved the reporting end without moving the closing count. Fixtures were corrected before the clean new-suite rerun.
- HTTP worker: **11 passed, one warning, 42.67 seconds**. Its first run had four passes, six setup errors and one failure from fixture mistakes: initial conversion creation used editor rather than owner, and one idempotency key was reused for document creation and resolution. Corrected roles/keys produced the clean run.
- Lead joint suite after final ASGI/detail repair: **51 passed, one warning, 140.84 seconds**, including HTTP, labels, internal catalog/bindings and readiness/cancellation.
- Lead final public detail/alias/backdating cases: **four passed, one warning, 8.52 seconds**.
- Full exact-code [Linux CI](https://github.com/alisunkazemi21-cloud/Herman-SME-Financial-Advisor-Perisan/actions/runs/40307392553), job `121519765097`: **543 passed, two skipped, 15 warnings, 105.34 seconds**, followed by Ruff and Marimo success.
- Full Windows regression: **544 passed, one real-OCR skip, five warnings, 777.37 seconds**, exit zero. Application source matched `f877b9b` throughout; only documentation changed during the run. Scoped counts overlap and must not be added into a total.

No real customer records were used. A synthetic source is not a passed OCR/local-model quality gate or an observed customer outcome.

## Actual ownership and independent review

The lead recorded decisions, implemented catalog/public HTTP routes, natural-key capture, pure ASGI headers, extra acceptance cases and integration. The dated-label worker owned selection/models, analysis/freshness integration and its test module; it then reviewed lead-owned catalog/API/capture code read-only. The HTTP worker owned only the new HTTP acceptance file. Installed Backend Architect/API Tester briefs guided these bounded assignments; they are not additional executable tools or proof of qualifications.

Review found a missing historical-use distinction on standalone pack definition detail. The lead added it consistently to standalone detail/history, and an independent read-only closure check found no further issue. It also checked the pure ASGI wrapper's forwarding behavior; the lead's readiness/cancellation tests passed. The lead reviewed the worker's label identity/time/source/budget logic. No reviewer test run is inferred from a source review.

## Artifact and publication record

Ruff and whitespace checks passed. Marimo exited zero with existing host user-config access warnings; the notebook is unchanged for this backend-only workflow. Graphify code-only extraction/report: **1,751 nodes, 5,778 edges, 113 communities**; generated files remain local, no semantic/model extraction and no measured token savings.

Code was pushed normally from `2688446` to `f877b9b`; no force push, rebuilt history, PR or scheduled job. No new migration is needed: schema 18 supplies the existing immutable definitions, alias projection, observations, checks and decisions. PostgreSQL remained locally reachable. The run README, research chapter, technical report, media narrative and current progress map record the same accepted code and observed Windows/Linux results. The notebook remains unchanged with its successful Marimo check recorded. All 143 local Markdown links in the synchronized checkpoint documents resolved, and `git diff --check` passed.
