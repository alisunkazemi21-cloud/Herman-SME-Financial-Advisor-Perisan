# Checkpoint 3: extracted rows → proposals → human review

Date: 2026-10-06. Apply migrations 4–5 with `python -m src.backend.cli migrate` before starting the updated API.

The completed workflow for CSV/XLSX is:

1. Upload immutable evidence to the business.
2. Enqueue extraction and let an authorized worker process it.
3. Read the successful job's `extraction.id` and tabular rows.
4. Submit an explicit mapping to `POST /businesses/{business}/tabular-imports` with a new `Idempotency-Key`.
5. Review the returned record IDs and their source values. Approve/reject each through the existing decision endpoint.
6. Run inventory analysis. Unreviewed input produces an incomplete result; approved input can contribute to calculations.

Example mapping (substitute real UUIDs):

```json
{
  "extraction_id": "UUID",
  "sheet": "CSV",
  "rows": [2, 3],
  "record_kind": "movement",
  "warehouse_id": "UUID",
  "sku_column": "sku",
  "quantity_column": "quantity",
  "unit_column": "unit",
  "time_column": "time",
  "movement_kind": "purchase"
}
```

Mapping column names refer to **extracted** row keys; existing Persian header normalization may change them (for example مبلغ becomes `amount`). Read the extraction first. `CSV` is the CSV sheet name; XLSX uses the actual worksheet name. Row numbers are source row numbers, with headers at row 1.

Specify exactly one of `unit` or `unit_column`, and exactly one of timezone-aware `occurred_at` or `time_column`. Supported units are `g`, `kg`, `ml`, `l`, `each`, `pack`; item-specific pack conversion remains separate. ISO timestamps require a UTC offset. Dates without a timezone, Persian unit synonyms, fuzzy SKU matching and ambiguous numeric separators are not guessed. Quantities use the existing exact Decimal validation.

`record_kind` may be `count`, `movement` or `fulfillment`. Movements require `movement_kind`; fulfillments require `fulfillment_kind` (`sale`, `complimentary`, `staff`, `production`). Source rows for fulfillment must describe fulfilled events, not unfulfilled orders. The type is explicitly selected by the operator, not inferred from an LLM. No approval flag is accepted in a mapping.

Each batch accepts 1–100 distinct row numbers, one sheet and one warehouse. All rows, provenance, audit events and idempotency data commit together. Unknown SKUs, missing columns, invalid quantities/times or a duplicate source row roll back the whole batch. No partial import is reported as success. Concurrent identical requests return one batch; conflicting content with the same key fails.

Import deduplication uses business + document ID + sheet + row number + record kind. It therefore blocks re-importing the same row under a new key or after a new extraction of the **same document**. Separately uploaded documents and manually entered records also receive duplicate-candidate checks as described below. Replacing an already imported/approved/rejected row is a future correction workflow; creating another extraction is not a workaround.

## Duplicate detection requested by the user

- **Identical file:** same-business SHA-256 matches are returned in the upload response and `GET /businesses/{business}/documents/{id}/duplicates`, even if the filename differs. Existing evidence is preserved; no upload is silently deleted or merged. No information about another business is exposed.
- **Repeated source row:** the unique import constraint blocks a second proposal for the same source row and record kind, including concurrent requests and re-extraction of the same document.
- **Matching event:** record details and import responses flag other non-rejected count/movement/fulfillment records with the same warehouse, item, exact event timestamp, kind and quantity. kg/g and l/ml are normalized; pack quantities use the item's recorded conversion when available. The fulfillment status is also compared. A quantity repeated on another date or under another event kind does not by itself trigger this rule.
- **Human disposition:** approval of a flagged record requires `duplicate_resolution: "distinct_event"` and a reason. To reject a duplicate use `approved: false` and `duplicate_resolution: "same_event"`. The decision is immutable. `same_event` cannot be approved. Neither detector silently removes legitimate repeated transactions.

Candidate responses show at most 100 matching files/records. Detection is conservative and exact: it does not identify similar scans with different bytes, near timestamps, fuzzy vendors/invoice numbers or semantically equivalent text. A full financial-amount duplicate detector will require the tenant-scoped monetary journal/invoice model; equal amounts alone are explicitly insufficient. Already approved records are not silently revoked when a later duplicate appears. Current candidate checks are visible on record retrieval; correction/supersession remains a future workflow.

`GET /businesses/{business}/tabular-imports/{id}` returns mapping and proposed record IDs. `GET /businesses/{business}/records/{id}` now includes `origin` with extraction ID, source document, sheet/row, original normalized values, mapping, parser version and source hash. The database enforces same-business foreign keys and consistency between record, document, extraction and batch. Provenance rows and batches are append-only.

Inventory analyses save relevant source provenance in `source_provenance` alongside the original calculation snapshot. Existing manually entered records have no extraction origin and continue to use their evidence document/locator. No past analysis is rewritten when new records are approved.

Eleven PostgreSQL import tests cover the end-to-end review path, all-or-nothing rollback, concurrent idempotency, duplicate prevention across extraction versions, repeated rows inside one file, explicit mapping semantics, tenant/role denial, and provenance in the resulting inventory analysis. Four additional duplicate-detection tests exercise renamed identical uploads, cross-business isolation, equivalent units, explicit reviewer disposition and legitimate repeated quantities. The test restaurant's original 7 kg variance becomes 12 kg after an additional reviewed 5 kg purchase; before approval the analysis is incomplete.

This inventory checkpoint does not implement PDF/image table mapping, recipe/BOM batch imports, correction/supersession or automatic classification. The later [journal import checkpoint](JOURNAL_IMPORTS.md) adds a separate explicit financial mapping and stronger hash-based source-row reuse detection for journals. [Business cases](BUSINESS_CASES.md) add conversation history. The [document queue limits](DOCUMENT_QUEUE.md) still apply. No interface changes were made.

Final local checkpoint: **108 passed, 1 skipped** on real PostgreSQL 17.11; Ruff passed. The skip remains the real OCR engine/reference-fixture test. A failing Windows long-path checkpoint revealed overly long temporary blob filenames; shortening only staging names fixed it and the full suite then passed with the long test-directory name preserved. FastAPI's test client emitted a non-failing httpx-adapter deprecation warning.
