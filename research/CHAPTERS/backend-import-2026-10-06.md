# From extraction to reviewed records

Checkpoint: `backend-import-2026-10-06`.

Extracted text is not accounting truth. Workers store candidate outputs; mapping to SKU, quantity, unit and timestamp is explicit, and records begin as proposals. Each batch is one transaction; invalid rows cannot leave partial imports. Approved records remain linked to extraction versions and source rows.

Duplicate detection has three layers: identical file bytes, repeated source-row imports and matching events after unit conversion. Only repeat import of the same source row into the same record kind is blocked by uniqueness. File/event candidates require human review because repeated values can be legitimate. Invoice numbers, counterparties and OCR similarity need a fuller financial model.

Methods and tests: [mapping contract](../TABULAR_IMPORTS.md), [worker contract](../DOCUMENT_QUEUE.md). These tests do not establish agent capacity, real OCR accuracy or full queue capacity for 1,000 businesses.
