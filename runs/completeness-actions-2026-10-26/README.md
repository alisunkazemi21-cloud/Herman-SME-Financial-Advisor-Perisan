# C17: completeness and reviewed follow-up

Status: implementation and regression in progress. C16 remains the last accepted checkpoint. No production/pilot acceptance is implied.

## Delivered code under validation

- Migration 19: immutable twelve-category warehouse-period assessments, separate human decisions, same-scope approved replacement chains and bounded server-derived operational signatures.
- Migration 20: immutable analysis-linked investigation proposals, named responsibility and follow-up, sequenced review/start/note/completion/cancellation history.
- New saved analyses intersect the original request declaration with reviewed completeness. Missing, changed, contradictory or pending evidence withholds numeric results. Reviews before period end remain provisional; current context, overview and portfolio hide their figures.
- Earlier receipts retain their original bytes. Pre-C17 completeness is unknown for current advice. Stateless tools still calculate explicit supplied assumptions without certifying a business's records.
- Public coverage/action routes use authenticated scoped services, idempotent writes, bounded reads, no-store responses and redacted validation failures. No reminder, customer message or financial posting is sent.

Contract: [completeness and actions](../../research/COMPLETENESS_ACTIONS.md) · [API guide](../../research/COMPLETENESS_ACTIONS_API.md). Existing catalog and historical pack interpretation remain separate from operational completeness.

## Validation evidence so far

- Action component: 10 PostgreSQL tests passed in 16.62 seconds; focused Ruff passed.
- Final coverage component after the query repair: **13 PostgreSQL tests passed in 144.35 seconds** on an isolated database created from template0 and migrated through version 20. This includes an unanalysed/uncommitted 10,001-row tenant under a stricter ten-second SQL limit. Host temporary-directory cleanup/dependency warnings were present; an earlier clean component run passed 12 tests in 39.81 seconds before the new regression.
- Public workflow: 10 PostgreSQL/FastAPI tests passed in 57.87 seconds; focused Ruff passed. Includes exact synthetic 7,000 g reconciliation, provisional suppression in advisor context/overview/portfolio, action outcomes, tenant/role/idempotency/error/tamper behavior.
- Independent integration review found portfolio previews bypassing the gated summary for provisional reports. The lead repaired that consumer; the HTTP suite now asserts both overview and portfolio suppression.
- An early integration run overlapped the addition of the required unreviewed-count metadata field to the development SQL function. Its loaded older Python model rejected that field: 55 passed, 34 failed and 24 setup errors. This is a failed mixed-version development run, not acceptance. It also identified earlier freshness expectations that omitted the new completeness dataset/review and a future-period case that previously included numeric receipts in current context. Those expectations are being updated to the C17 contract.
- The initial fresh full regression completed with **563 passed, 13 failed, one real-OCR skip in 1719.85 seconds**. It ran before fixture/expectation repairs and the query fix: failures cover added completeness change metadata/budget, explicit synthetic review setup for existing catalog/import/concurrent analysis cases, conditional future receipts and the deliberately cancelled slow dossier query. This is diagnostic evidence, not acceptance. Affected fixtures now use the actual owner proposal/review workflow; no application bypass was added.
- Query-plan reproduction: the original unanalysed 10,001-row tenant exceeded a 15-second limit, while fenced exact primary-key lookups completed in 1.863 seconds. Completeness SQL now preserves stricter caller budgets and recovers cancelled reads through savepoints.
- Final lead component/API/metadata/timeout scope: **33 passed, one warning, 209.53 seconds**. Additional repaired regression scope passed 39 with one old budget-expectation failure; after accounting for dossier facts/review rows, its two budget cases passed. Import-provenance and readiness checks passed **10 tests in 21.94 seconds**. Counts overlap.
- Final complete local regression and CI remain pending. The notebook check exited zero with existing host configuration-access warnings; the notebook is unchanged for this backend-only checkpoint. Ruff passed. Exact code revision and final Graphify/report/link checks will be recorded with acceptance.
- First Linux CI at implementation `c585774` passed **588**, failed one timezone-string assertion and skipped two in 158.29 seconds. The API returned the same instants in UTC rather than Tehran notation. The test-only follow-up compares typed proposals and runs both session timezones; its **two local cases passed in 20.37 seconds**. No application behavior changed. The Windows full run started at `c585774`; its application sources remain identical while this independent test improvement is validated.

These suites overlap; do not add their counts. The isolated test DSN and runtime logs remain ignored local files; no credential is published.

## Open gates

Real permissioned pilot records and repeated reviewed outcomes remain unconfirmed. C17 does not validate actual OCR/model quality, all accounting requirements, coordinated restore, representative 1,000-business ingestion/reporting load or the minimal Persian owner interface. No savings, renewal, revenue or customer usage is inferred from synthetic test results.
