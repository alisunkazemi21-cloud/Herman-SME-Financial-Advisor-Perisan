# Reviewed journal reports for the advisor and portfolio

Migrations 010 and 011 connect approved journals to immutable report receipts, the five-indicator portfolio and business advisor context. Apply migrations with `python -m src.backend.cli migrate` using the existing administrative environment configuration before serving the updated API. Runtime requests continue to use the restricted database role. The visible interface remains deferred.

## Reviewed account mapping

A mapping contains a Persian title, a document/locator supporting the classification, and a category for every current business account. Categories and account-kind requirements are:

| Category | Required kind | Meaning in this management report |
|---|---|---|
| `cash` | asset | Selected current cash accounts |
| `current_asset` | asset | Other current assets |
| `noncurrent_asset` | asset | Assets excluded from the current ratio |
| `current_liability` | liability | Liabilities included in the current ratio |
| `noncurrent_liability` | liability | Other liabilities |
| `equity` | equity | Equity balances |
| `revenue` | revenue | Revenue-account movements |
| `expense` | expense | Expense-account movements |

At least one cash account is required. Labels never determine categories automatically. Creating a report requires a separately approved mapping that exactly covers the current account catalog. Adding an account requires a new complete mapping for subsequent reports. Cash classification here is limited to selected current cash; special cases such as restricted cash or cash equivalents require accounting review and may require extending this contract.

## Receipt and calculations

A report selects every approved entry through its inclusive end date in one database snapshot. Entries before start supply opening balances; entries from start through end supply period movements. Pending and rejected entries do not contribute. An empty approved ledger produces a missing-data conflict, not a fabricated report.

The immutable input manifest preserves period, mapping and its review, account classifications, exact journal lines and locators, entry approvals, and document hashes. Separate SHA-256 values identify the canonical manifest and calculated result. A receipt does not change after new postings. Source bytes and stored hashes are verified on report approval, retrieval and advisor/portfolio use. Hashes support integrity checks within the application boundary; they do not defeat a privileged administrator who replaces the whole database and evidence store.

| Constant | Calculation |
|---|---|
| Opening cash | Opening debit-minus-credit across mapped cash accounts |
| Cash inflows | Sum of positive period cash nets, one net per journal |
| Cash outflows | Absolute sum of negative period cash nets, one net per journal |
| Revenue | Period credit-minus-debit across revenue accounts |
| Net income | Revenue minus period debit-minus-credit across expense accounts |
| Current assets | Closing debit-minus-credit for cash and other current assets |
| Current liabilities | Closing credit-minus-debit for current liabilities |

The shared indicator calculator derives revenue, net income, net cash flow, current ratio and net margin, plus opening/inflow/outflow/closing waterfall data. Journal arithmetic uses Decimal with precision 60; monetary results are strings, and nonpositive ratio denominators yield undefined values. The prior statement calculator retains precision 40. The report also saves per-account opening/debit/credit/closing values and names the contributing accounts for each financial field. Report ID and manifest hashes link a compact summary to the full line-level receipt.

Cash transfers between mapped cash accounts cancel. Inflows/outflows are explicitly labelled net cash movement per journal, including in Persian chart labels. They are not gross bank receipts/payments: a batch journal can hide offsetting external movements. Revenue and expense movements can be distorted by closing entries or missing records. This is a management summary, not a statutory income/cash-flow statement or accounting-compliance claim. A reviewer must check these limitations and confirm report scope before approval.

## Review, freshness and replacement

Editors, reviewers and owners may propose mappings and create reports. Only owners/reviewers can approve. Both reviews require `reviewed_values: true`; report approval additionally requires `scope_confirmed: true`. Human scope confirmation is an attestation, not automatic proof of completeness. Rejection remains possible when source bytes are unavailable or changed, because rejection does not publish financial values.

Freshness compares the saved approved-entry set with current approved entries through the same end date. A later approved backdated entry makes the report stale. Entries after end and pending proposals do not. A stale report cannot be newly approved and cannot supply numeric portfolio/advisor summaries; its historical receipt remains readable with a stale flag.

A replacement request supplies `supersedes` pointing to an approved report for the identical period. The new receipt requires its own review. Only one replacement can be approved per predecessor; an approved replacement removes its predecessor from default selection. Old receipts remain immutable and link to the replacement. Explicit advisor selection of an old replaced receipt returns `superseded` without numeric values. Rejected replacements do not supersede anything. Further corrections form a chain by naming the latest approved report.

Default portfolio selection considers both reviewed statements and reviewed journal reports at or before the business-local effective date. Two unlinked candidates at the latest period end are a conflict, even if they use different source types. No automatic preference or fallback hides the conflict. A selected stale latest report returns unavailable values rather than falling back to older numbers.

## API

The following routes are under `/businesses/{business}/journal`. All require bearer authentication; POST requests require `Idempotency-Key`. Successful responses use `Cache-Control: no-store`. Completed creation retries return the same receipt, even after the underlying ledger changes. Use a new key to intentionally calculate a fresh report.

| Method | Route | Input/result |
|---|---|---|
| POST | `/mappings` | `title_fa`, `accounts` code/category object, `evidence`; returns ID |
| GET | `/mappings` | Metadata page |
| GET | `/mappings/{id}` | Mapping and current review |
| POST | `/mappings/{id}/decision` | `approved`, `reviewed_values`, `reason_fa` |
| POST | `/reports` | `mapping_id`, `period_start`, `period_end`, optional `supersedes`; returns ID |
| GET | `/reports` | Metadata page without manifests |
| GET | `/reports/{id}` | Full receipt, current review, freshness and replacement link |
| POST | `/reports/{id}/decision` | `approved`, `reviewed_values`, `scope_confirmed`, `reason_fa` |

Pages default to 20 and allow 1–50 with an `after` UUID cursor; ordering is UUID order. `BusinessContextInput.journal_report_id` explicitly selects an approved report. Its end cannot be after the requested business-local date. The model receives a bounded financial summary and receipt identifiers, not the full manifest. `include_financial` still selects the default portfolio summary. Saved cases preserve these selectors and context receipts; requests without the new selector retain their earlier serialization for idempotency compatibility. Quick has no report selector or database retrieval.

Synchronous limits: 1,000 accounts, 5,000 entries, 10,000 lines, 1,000 distinct source documents, an 8 MiB canonical manifest and a 512 KiB result. Oversized reports fail without publishing a partial receipt. PostgreSQL JSON-text limits allow serialization overhead. Advisor/context responses retain the separate 64 KiB bound. These are request limits, not full application capacity evidence; larger reports need a future batch path.

## Verification and remaining work

Acceptance checks cover cash transfers, accrual sales, liabilities, incomplete/incompatible mappings, review gates, hash receipts, idempotency, backdated changes, competing sources, source tampering, tenant isolation, oversize failure, case integration, serialization compatibility and concurrent replacement approval. Full results are recorded in [validation](VALIDATION.md).

Remaining accounting work includes period-close controls, journal import mapping and proposal generation, bank-detail cash-flow classification, larger reports, and correction workflows for non-journal records. Real model/OCR evaluation and Iranian standards verification remain separate gates. The implementation does not assert those gates have been satisfied.
