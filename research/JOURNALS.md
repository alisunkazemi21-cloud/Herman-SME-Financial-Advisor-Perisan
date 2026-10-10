# Tenant financial journals

Migration 009 adds an immutable business account catalog, journal headers, evidenced lines and human review decisions. These PostgreSQL records use authenticated memberships; they do not import the earlier single-user JSONL ledger or trust its actor strings.

## Workflow and API

Create accounts, upload source documents, propose a balanced entry, inspect its evidence and duplicate candidates, and submit a reviewer decision. Only approved entries enter the trial balance. All routes require bearer authentication. Successful responses use `Cache-Control: no-store`; POST routes require `Idempotency-Key` and atomically record audit events.

Routes below are relative to `/businesses/{business}/journal`:

| Method | Route | Contract |
|---|---|---|
| POST | `/accounts` | `code`, Persian `name_fa`, and `kind`; return account ID |
| GET | `/accounts` | Code cursor `after`, page size 1–100, default 50 |
| POST | `/entries` | Validated JournalInput; return entry ID |
| GET | `/entries` | UUID cursor `after`, page size 1–100, default 50; metadata only |
| GET | `/entries/{id}` | Header, exact line amounts, source hashes, review and related records |
| POST | `/entries/{id}/decision` | `approved`, `reviewed_values: true`, Persian reason, optional duplicate resolution |
| POST | `/entries/{id}/reversals` | New dates and Persian description; server builds the inverse proposal |
| GET | `/trial-balance` | Inclusive Gregorian `start` and `end` dates |

Owners, reviewers and editors can create accounts and propose entries/reversals. Owners and reviewers can decide. Viewers can read. Decisions are final immutable events; rejected entries do not post and must be replaced by new proposals. An account's code, label and kind are immutable in this version. Account kinds are asset, liability, equity, revenue and expense; they are descriptive classifications, not an automated statutory chart.

## Entry contract

JournalInput carries `entry_date`, matching `jalali_date`, `description_fa`, `currency: IRR`, and 2–100 lines. Each line names a defined business account, `side` (`debit` or `credit`), a positive decimal amount, and `evidence` containing `document_id` and a row/page `locator`. Amounts accept strings or integers, never floats or booleans, with at most 22 integer places and six decimal places. Each account appears at most once per entry. Debit and credit totals must agree exactly. Split entries can debit multiple accounts and credit multiple others.

The API validates Gregorian/Jalali agreement and balanced Decimal totals. The database independently enforces line counts, balance, finite positive numeric bounds, tenant references, pattern fingerprints and reversal equality. A trigger stamps the header's creating transaction; lines can only be inserted by the same author within that transaction. This prevents a later balanced pair of extra lines from silently changing an immutable entry. Deferred constraints inspect the final line set, and update/delete triggers reject mutation.

Source bytes are hashed at proposal, approval and trace retrieval. Rejection can proceed when a source is broken because it does not post amounts. Trial balances verify their source files before returning values. A missing or changed source causes a conflict, not fabricated or partial values. Storage administrators remain outside the application trust boundary.

## Duplicate review and corrections

The SHA-256 accounting-pattern fingerprint includes date, currency and sorted account/side/amount triples normalized to six decimals. Descriptions, document names, document IDs, line order and numeric scale do not distinguish events. This catches the same posting supplied through a different file. Matching patterns are candidates, not proof of duplication: two real transactions can legitimately share these fields. Trace returns up to 20 candidates with an explicit truncation flag.

Approving a repeated pattern requires `duplicate_resolution: distinct_event`; `same_event` is compatible only with rejection. The database derives decision fingerprints from their header and enforces at most one approved entry without explicit distinct-event review for each pattern. Concurrent requests cannot silently create two such first approvals. This does not recognize semantically equivalent entries with different account codes, dates or splits; broader document/invoice matching remains separate work.

A reversal starts from an approved original and copies its exact accounts, amounts and evidence with opposite sides. Its date cannot precede the original. Reversals require their own human approval; at most one reversal can be approved for an original. Rejected reversal proposals can be replaced. Reversing a reversal is not supported. A correction consists of a reviewed reversal plus a separately proposed/reviewed replacement. This checkpoint does not change approved inventory records or knowledge claims.

## Trial balance semantics

For each account, `opening_net` sums approved debit minus credit before start. `period_debit` and `period_credit` sum movements from start through end, inclusively. `closing_net` equals opening plus period debits minus period credits. Positive net is debit and negative net is credit. All monetary outputs are decimal strings computed with PostgreSQL numeric arithmetic; they never pass through floating point. Unused accounts appear with zero values.

The response includes period totals, the number of approved entries through end, source hashes and Persian limitations. It reads one database snapshot using current approvals and effective entry dates. A later approved backdated entry may change a future retrieval for the same dates. No historical publication receipt, closed accounting period or immutable report snapshot is implied.

An empty approved ledger yields zero calculated balances and an approved-entry count of zero. That does not establish that the business has no assets, liabilities or activity. The response explicitly warns that ledger completeness and real business position have not been established.

Synchronous reports support up to 1,000 accounts and 1,000 distinct source documents per business through the end date. Larger reports fail explicitly and need a future batch-report path; they are never truncated to plausible totals. The per-business bound does not limit the system to 1,000 businesses. Journal throughput and full application capacity have not been benchmarked.

This is a trial balance, not an automatically classified income statement, cash-flow statement or statutory filing. The portfolio's existing five indicators still use separately reviewed financial snapshots. Account mapping, period closing, journal import mapping, automated journal proposals, persisted trial-balance reports and advisor selection of journal results remain future work. Interface work remains deferred.

## Evidence

The acceptance suite exercises exact large values, split entries, approval gates, idempotency, concurrent duplicate review, rejected-reversal retry, date boundaries, database constraints, source tampering, tenant isolation and API serialization. See [validation](VALIDATION.md) for final results. Database mechanics follow the PostgreSQL 17 [constraint-trigger documentation](https://www.postgresql.org/docs/17/sql-createtrigger.html) and [row-security documentation](https://www.postgresql.org/docs/17/ddl-rowsecurity.html); these sources do not establish accounting compliance.
