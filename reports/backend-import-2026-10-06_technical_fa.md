# Document imports and duplicate detection: technical report

Checkpoint: `backend-import-2026-10-06`.

Migration 3 adds the queue and immutable extraction outputs; migration 4 adds mapping and record provenance; migration 5 adds document-hash indexing and duplicate decisions. Workers use restricted roles and explicit business scopes. Worker output is never automatically approved. Imports are atomic; concurrent retries do not create extra records, and new extraction versions cannot bypass source-row uniqueness.

Event matching compares item, warehouse, kind, timestamp and quantity, normalizing kg/g and l/ml. Approval of flagged candidates requires `distinct_event` and a reason; `same_event` must be rejected. Decisions and evidence are not deleted or overwritten.

Full testing found long Windows temporary filenames; staging names were shortened while final names retain full content hashes. Acceptance details and final test results are in the [checkpoint contract](../research/TABULAR_IMPORTS.md). Real OCR evaluation and a conversational agent remain incomplete.
