# C17: completeness and reviewed follow-up

Status: **C17 accepted within its backend scope**. Implementation `c585774575c0bce7fcb3fe5171fab0e1ea831069`; timezone-test follow-up `9611c11fa51d09a6d246f29bfaaf0523fe1c016b`. No production/pilot acceptance is implied.

Full Windows PostgreSQL regression: **590 passed, one real-OCR skip, five warnings, 1133.34 seconds**, exit zero. This run started at `c585774`; application sources stayed identical while the test-only UTC/Tehran follow-up was made. Its two additional local timezone cases passed separately. Final [Linux CI](https://github.com/alisunkazemi21-cloud/Herman-SME-Financial-Advisor-Perisan/actions/runs/40357187856), job `121692701606`, passed **590 tests, two skipped, 15 warnings, 148.72 seconds**, then Ruff/Marimo, at `9611c11`. The CI collection contains the extra timezone parameter case; platform skips also differ.

## Delivered and validated code

- Migration 19: immutable twelve-category warehouse-period assessments, separate human decisions, same-scope approved replacement chains and bounded server-derived operational signatures.
- Migration 20: immutable analysis-linked investigation proposals, named responsibility and follow-up, sequenced review/start/note/completion/cancellation history.
- New saved analyses intersect the original request declaration with reviewed completeness. Missing, changed, contradictory or pending evidence withholds numeric results. Reviews before period end remain provisional; current context, overview and portfolio hide their figures.
- Earlier receipts retain their original bytes. Pre-C17 completeness is unknown for current advice. Stateless tools still calculate explicit supplied assumptions without certifying a business's records.
- Public coverage/action routes use authenticated scoped services, idempotent writes, bounded reads, no-store responses and redacted validation failures. No reminder, customer message or financial posting is sent.

Contract: [completeness and actions](../../research/COMPLETENESS_ACTIONS.md) · [API guide](../../research/COMPLETENESS_ACTIONS_API.md). Existing catalog and historical pack interpretation remain separate from operational completeness.

## Validation and development evidence

- Action component: 10 PostgreSQL tests passed in 16.62 seconds; focused Ruff passed.
- Final coverage component after the query repair: **13 PostgreSQL tests passed in 144.35 seconds** on an isolated database created from template0 and migrated through version 20. This includes an unanalysed/uncommitted 10,001-row tenant under a stricter ten-second SQL limit. Host temporary-directory cleanup/dependency warnings were present; an earlier clean component run passed 12 tests in 39.81 seconds before the new regression.
- Public workflow: 10 PostgreSQL/FastAPI tests passed in 57.87 seconds; focused Ruff passed. Includes exact synthetic 7,000 g reconciliation, provisional suppression in advisor context/overview/portfolio, action outcomes, tenant/role/idempotency/error/tamper behavior.
- Independent integration review found portfolio previews bypassing the gated summary for provisional reports. The lead repaired that consumer; the HTTP suite now asserts both overview and portfolio suppression.
- An early integration run overlapped the addition of the required unreviewed-count metadata field to the development SQL function. Its loaded older Python model rejected that field: 55 passed, 34 failed and 24 setup errors. This is a failed mixed-version development run, not acceptance. It also identified earlier freshness expectations that omitted the new completeness dataset/review and a future-period case that previously included numeric receipts in current context. Those expectations are being updated to the C17 contract.
- The initial fresh full regression completed with **563 passed, 13 failed, one real-OCR skip in 1719.85 seconds**. It ran before fixture/expectation repairs and the query fix: failures cover added completeness change metadata/budget, explicit synthetic review setup for existing catalog/import/concurrent analysis cases, conditional future receipts and the deliberately cancelled slow dossier query. This is diagnostic evidence, not acceptance. Affected fixtures now use the actual owner proposal/review workflow; no application bypass was added.
- Query-plan reproduction: the original unanalysed 10,001-row tenant exceeded a 15-second limit, while fenced exact primary-key lookups completed in 1.863 seconds. Completeness SQL now preserves stricter caller budgets and recovers cancelled reads through savepoints.
- Final lead component/API/metadata/timeout scope: **33 passed, one warning, 209.53 seconds**. Additional repaired regression scope passed 39 with one old budget-expectation failure; after accounting for dossier facts/review rows, its two budget cases passed. Import-provenance and readiness checks passed **10 tests in 21.94 seconds**. Counts overlap.
- Final complete local regression and CI passed as recorded above. The notebook check exited zero with existing host configuration-access warnings; the notebook is unchanged for this backend-only checkpoint. Ruff/whitespace passed. Graphify code-only extraction/report: **1,931 nodes, 6,422 edges, 121 communities**; generated files remain ignored, with no model extraction or measured token-saving claim.
- First Linux CI at implementation `c585774` passed **588**, failed one timezone-string assertion and skipped two in 158.29 seconds. The API returned the same instants in UTC rather than Tehran notation. The test-only follow-up compares typed proposals and runs both session timezones; its **two local cases passed in 20.37 seconds**. No application behavior changed. The Windows full run started at `c585774`; its application sources remain identical while this independent test improvement is validated.

These suites overlap; do not add their counts. The isolated test DSN and runtime logs remain ignored local files; no credential is published.

## Acceptance mapping

| Required behavior | Direct evidence |
|---|---|
| Twelve exact categories; explicit no-event claims; honest incomplete review | [Coverage tests](../../tests/test_coverage.py): review_required, missing_categories, no_events_contradiction, recipe_requirement. |
| Approval/correction/boundary changes invalidate support, including unfulfilled pending headers | Coverage signature/pending tests; [freshness regression](../../tests/test_inventory_freshness.py); imported records require renewed completeness review. |
| Three booleans cannot bypass review; original declaration and hash retained | [Managed completeness](../../tests/test_managed_completeness.py) and [HTTP missing-review test](../../tests/test_completeness_actions_api.py). |
| Provisional/legacy numbers withheld from context, overview and portfolio; raw receipts retained | Managed legacy tests, coverage clock-passage test and HTTP future-period/portfolio cases. |
| Typed metadata scope/version/derivation guards; same instant across session timezones | Managed invalid-metadata cases; HTTP roundtrip parametrized UTC and Asia/Tehran. |
| Source hashes, roles, tenancy, immutable history, root/successor and sequence races | Coverage/action component SQL/service tests plus HTTP role/tamper/idempotency cases. |
| Named responsibility, reviewed work and confirmed/no-change/inconclusive outcomes without inferred savings | [Action lifecycle](../../tests/test_actions.py), terminal-state and evidence cases; HTTP incomplete-analysis investigation roundtrip. |
| Row/byte limits, unanalysed bulk tenant, SQL cancellation recovery and no partial write | Coverage bulk/shared-budget tests, [timeout tests](../../tests/test_coverage_budget.py), existing analysis/freshness bounds. |
| Restricted schema/storage readiness and preserved development history | Nine aligned-development readiness checks passed in 10.08 seconds. Three completeness functions and the missing finite-period check were aligned without changing stored workflow/analysis counts. |

## Artifact record

README, progress/plan, decisions, API contract, research chapter, validation log and technical/media reports are synchronized. The Persian notebook remains unchanged with a successful Marimo check. All 132 local documentation links checked in the synchronized artifact set resolved. No PR, branch rewrite, force push, external reminder or customer message was created.

## Open gates

Real permissioned pilot records and repeated reviewed outcomes remain unconfirmed. C17 does not validate actual OCR/model quality, all accounting requirements, coordinated restore, representative 1,000-business ingestion/reporting load or the minimal Persian owner interface. No savings, renewal, revenue or customer usage is inferred from synthetic test results.
