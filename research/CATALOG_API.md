# Reviewed catalog and historical usage API

Implementation: code `f877b9b`, schema 18. The exact-code Linux workflow passed; final local checkpoint evidence is in [the run record](../runs/catalog-workflow-2026-10-26/README.md). All paths below start with `/businesses/{business}`. Bearer authentication is required; every write also requires `Idempotency-Key`. The server supplies the actor from the credential. Models cannot approve through any advisor tool.

## Operations

| Method and suffix | Role | Result |
|---|---|---|
| `GET /catalog/items` | Member | Stable-item-ID page with selected labels, `effective_at` and `next_cursor`; limit 1–100. |
| `GET /catalog/items/{item}` | Member | Selected label and eligible pack definition at the requested instant. Historical usage is explicitly not evaluated. |
| `GET /catalog/items/{item}/labels` | Member | Immutable label proposal/decision history, source, predecessor/successor and validity; limit 1–100, `after` is the last returned definition ID. |
| `GET /catalog/items/{item}/packs` | Member | Pack-definition history with exact decimal strings and the historical-use distinction; same history pagination. |
| `GET /catalog/item-revisions/{definition}` | Member | One item definition and its publication/decision lineage. |
| `GET /catalog/pack-revisions/{definition}` | Member | One pack definition, observation and lineage; historical usage is not evaluated. |
| `POST /catalog/item-revisions` | Editor/owner/reviewer | `ItemProposal`: ID, stable item ID, eligible predecessor ID, SKU, Persian name and evidence reference. |
| `POST /catalog/item-revisions/{definition}/decision` | Owner/reviewer | `ItemDecision`: approve/reject, nonblank Persian reason and optional aware future activation. |
| `POST /catalog/pack-revisions` | Editor/owner/reviewer | `PackProposal`: ID, stable item ID, eligible predecessor, exact positive base quantity and evidence. |
| `POST /catalog/pack-revisions/{definition}/decision` | Owner/reviewer | `PackDecision`, with the same human/prospective rules. |
| `GET /pack-bindings` | Member | Scoped checks and approved resolution pointers, optional `record`, stable check-ID cursor; limit 1–50. |
| `POST /pack-bindings` | Editor/owner/reviewer | Capture a concrete past source key; the server derives item/time/state/factor. Future or invalid topology is rejected. |
| `GET /pack-bindings/{check}` | Member | Immutable check, optional approved resolution and current effective state. |
| `GET /pack-bindings/{check}/reviews` | Member | Append-only decisions with stable review-ID cursor; limit 1–50. |
| `POST /pack-bindings/{check}/reviews` | Owner/reviewer | Source-backed approval of an eligible definition, or rejection that leaves the resolution slot available. |

Successful writes return their server-selected `id` and status 201, including an identical idempotent retry. Reusing the key for a different payload returns 409. A compatible revision cannot submit replacement base units or consumption modes; those fields are outside the proposal contract. Original item IDs and immutable raw resource reads remain unchanged.

## Time and history

Current list/detail reads accept optional aware `effective_at`; omitted time comes from the database clock. Reuse the returned instant when paging for one effective selection time. Each HTTP request still has its own database snapshot. Instants compare in Gregorian time; intervals are half-open. A naive timestamp is invalid. Initial definitions have no fabricated approval/source/start; approved successors begin no earlier than their server decision time.

New analysis labels are selected at `scope.end`, the reporting/closing instant, and stored in `item_labels` with `catalog.item_labels.v1` and source pointers before hashing. Imports separately resolve SKU at each source row's event time and retain original source values. A later current label does not rename an old saved receipt. Alias changes retire their predecessor at activation; an old SKU cannot be silently reused for a newer row.

A pack definition may be published and interval-eligible while a particular old quantity remains unsupported. Inspect the concrete `pack-binding` and its evidence. `historical_usage_status=not_evaluated` on catalog reads is not a financial conclusion. An unresolved check does not acquire a factor from a later baseline alone. A human resolution cites an eligible definition, reason and review evidence; new analysis uses that decision while the earlier receipt remains exact. A mistaken approved resolution needs an explicit inventory correction, not deletion of history.

## Response and failure contract

Decimal values are JSON strings. New catalog/binding successes and handled errors use `Cache-Control: no-store`. Validation failures are generic Persian responses without submitted-value echoes. Authentication is 401, disallowed role/membership 403, missing scoped detail 404, integrity/idempotency conflict 409, and invalid typed data or bounds 422. No source bytes or database details are copied into those errors. A failed approval/capture/analysis transaction leaves no partial decision, idempotency or audit record.

Current reads are metadata comparisons and do not recheck evidence bytes; current catalog responses say `evidence_verification=not_rechecked`. Proposal/approval and analysis writes verify the source roles required by their contracts. No read approves, captures a check or writes a replacement analysis. History remains bounded and inspectable.

## Acceptance and boundaries

The [C16 acceptance mapping](../runs/catalog-workflow-2026-10-26/README.md#acceptance-mapping) covers public and restricted-SQL behavior, including independent 64→58 arithmetic, half-open labels, original/import/case preservation, explicit historical resolution, alias conflicts, concurrent decisions/capture, source tampering and redacted no-store failures. This API completes compatible catalog review in the backend; it does not implement cross-identity stock migration, the visible Persian owner workflow, real-engine acceptance, coordinated restore, full workload capacity or customer outcomes.
