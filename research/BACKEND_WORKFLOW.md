# Herman backend design: business history and Quick Advisor

## Product direction and status

On 2026-10-05 the user deferred interface development and prioritized the backend workflow, multi-business data model, exact metric definitions and recipe/sales inventory reconciliation. The earlier local calculator and single-user JSONL ledger are not the foundation for a 1,000-business service.

This is a design contract. Implementation and acceptance evidence are tracked separately in [backend acceptance](BACKEND_ACCEPTANCE.md), [document queue](DOCUMENT_QUEUE.md) and [tabular imports](TABULAR_IMPORTS.md).

## Two modes, shared calculation tools

| Concern | Business workspace | Quick Advisor |
|---|---|---|
| Context | Authorized profile, branches, documents and records for one business | Only the question and files in the current session |
| Memory | Confirmed facts, decisions and versioned analyses | No business-history retrieval or permanent financial posting |
| Writes | Proposals, human review, confirmed events | Draft response; saving to a business requires a separate explicit action/review |
| Missing data | Request specific missing evidence | Ask a follow-up or give a conditional answer with stated assumptions |
| Retention | Business retention policy | Proposed short-lived session memory; exact conversational TTL remains a product decision |

Both modes use the same financial functions. Access scope and persistence differ. The implemented Quick calculator is stateless; it is not yet a conversational advisor.

## End-to-end request workflow

1. Authenticate and resolve membership/role. A submitted business ID is not authorization.
2. Define the question, period, branch, warehouse and target metric; classify the request.
3. Identify the minimum required evidence and report missing inputs before calculation.
4. Ingest a file/API payload with hash, upload ID, type, size, time, actor and processing state. Retries must not duplicate financial events.
5. Preserve original bytes and extracted text/rows/cells with candidate values and confidence. Document text is data, never executable instructions.
6. Normalize digits, dates, IRR/IRT and quantities. Match the business catalog explicitly; raw meat, minced meat and cooked meat are not automatically interchangeable.
7. Propose typed records with provenance. Review conflicts, duplicates and missing information before approval.
8. Commit approved events atomically and update rebuildable views. Corrections are new events.
9. Calculate using versioned tools, reviewed inputs and a time-specific snapshot. Persist results and uncertainty/errors.
10. Explain what happened, the supporting evidence, what remains unknown and what action a manager can review.
11. Link feedback/corrections to earlier versions and recalculate. Do not silently rewrite an earlier answer.

## Shared data model

Use linked entities with stable IDs, not one large JSON document per business.

| Domain | Planned entities | Main rule |
|---|---|---|
| Access | users, businesses, memberships, credentials | A user can belong to several businesses; roles belong to memberships. |
| Business structure | profiles, branches, warehouses, fiscal periods | Version industry, currency, calendar, timezone and policies. |
| Evidence | documents, versions, extraction runs, extracted fields, links | Separate original bytes; retain field locator and extraction version. |
| Catalog | items, aliases, units, item conversions | SKU and pack conversions are business/item specific. |
| Inventory | movements, counts, count lines, lots | Distinguish physical counts, waste, returns and transfers. |
| Recipes/production | recipes, versions, lines, production batches | Use the version valid at production/service time; define raw/net quantities and yield. |
| Sales/purchases | sales, lines, receipts, receipt lines | Preserve fulfillment status, event date, units and evidence. |
| Finance | journal entries/lines, approvals, reversals | Balanced entries, immutable confirmed history and evidence. |
| Analysis | metric definitions, runs, findings, finding evidence | Record metric version, inputs, outputs and limitations. |
| Business knowledge | facts, versions, confirmed policies | Separate confirmed facts from assumptions/extracted claims. |
| Conversation | cases, conversations, messages, tool runs | Text history does not replace inventory, journals or verified numbers. |
| Execution | jobs, attempts, audit events, outbox | Safe retries, bounded attempts, correlation and failure reasons. |

Unknown document types may be stored/classified but cannot enter confirmed calculations without a valid mapping. The common core is money, item, quantity, time, counterparty and evidence; restaurant/cafe/retail capabilities extend it.

## Business memory

Keep three layers separate: confirmed structured facts, retrievable text with evidence/validity dates, and conversation history. For numbers, call structured tools first. Semantic retrieval locates explanations/evidence; a conversation summary does not become a financial fact without approval. Conflicting documents produce a finding rather than an automatic choice of one source.

## MVP infrastructure

Start with one modular Python application, PostgreSQL for structured data, replaceable local/S3-compatible blob storage and separate workers for OCR/long analysis. PostgreSQL can provide the initial durable queue. Add Redis, vector storage, microservices or sharding only when measured need justifies them.

Every business-owned table carries `business_id`. Composite foreign keys prevent cross-business links. Use a non-owner runtime role without superuser/BYPASSRLS privileges, membership checks, RLS and negative tests. Set scope transaction-locally so reused connections do not leak it. Scope files, caches, jobs and text retrieval consistently.

Store amounts/quantities with NUMERIC/Decimal and explicit precision/rounding contracts. Keep timezone-aware event timestamps separate from Jalali display and from recording time. A late document should eventually mark affected periods for recalculation.

## Database indexes versus business metrics

Business KPI definitions are in [METRICS_CATALOG](METRICS_CATALOG.md). Database indexes address query access paths:

- Membership uniqueness: `(business_id, user_id)`.
- Inventory period reads: `(business_id, warehouse_id, item_id, occurred_at, id)`.
- Fulfilled sales: business/branch/time/ID, with same-business line references.
- Recipe validity: business/product/effective time; the design calls for no conflicting approved intervals.
- Documents: scoped processing/time indexes, scoped idempotency and content-hash lookup. Identical bytes do not always identify the same business event.
- Audit: business/time/ID.
- Queue: partial indexes for ready states and next attempt time.

Use EXPLAIN ANALYZE and realistic workloads to choose final indexes. Indexing every column is not the goal.

## Capacity contract

The target is at least 1,000 businesses, but tenant count alone is insufficient. The initial profile is 1,000 tenants, one million inventory movements, skewed tenant sizes and 25 concurrent requests. Report hardware, document volumes, p50/p95/p99 and errors. OCR must not occupy the normal read API path.

Acceptance requires no cross-business access, no duplicate posting on retry, correct quantities/balances and complete provenance. The completed synthetic PostgreSQL read benchmark is documented separately; it does not certify full ingestion, reconciliation, OCR or agent capacity.

## Implementation sequence

1. Profiles, memberships, tenant scope, migrations and audit.
2. Document evidence, durable processing, extraction candidates and review.
3. Catalog, units, warehouses, counts, receipts/transfers/waste, fulfilled sales and recipe versions.
4. End-to-end explanation of a monthly ingredient discrepancy.
5. Agent tools, confirmed knowledge and Quick without business-history retrieval.
6. Full 1,000-business concurrency, recovery and backup/restore validation, then broader financial tools.

## Technical references

- [PostgreSQL RLS](https://www.postgresql.org/docs/current/ddl-rowsecurity.html): policies alone do not constrain superusers/owners in the same way as a restricted runtime role.
- [NUMERIC](https://www.postgresql.org/docs/current/datatype-numeric.html): exact numeric storage with explicit precision/scale.
- [Multicolumn indexes](https://www.postgresql.org/docs/current/indexes-multicolumn.html): column order should reflect actual filters.
