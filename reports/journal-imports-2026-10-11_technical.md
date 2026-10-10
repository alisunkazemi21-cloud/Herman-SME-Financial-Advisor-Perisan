# Technical checkpoint: evidenced journal imports

Milestone **C10** in the [development map](../research/PROGRESS.md). Full regression result: **195 passed, one real-OCR fixture test skipped**.

The backend now supports explicit long-form CSV/XLSX mapping from a successful extraction to balanced journal proposals. Six distinct columns define voucher, account, debit, credit, date and description. Calendar and IRR/IRT unit are required. Selections contain whole vouchers from one sheet; dates/descriptions agree within each voucher and each account occurs once. Limits are 500 source rows per request and 100 lines per voucher.

Preview performs validation without persistence. Import repeats validation and inserts the batch, journals, origins, audit records and idempotency receipt atomically. Imported records never approve themselves. Authentication, membership and reviewer boundaries use the existing backend transaction model.

Migration 012 introduces tenant-scoped, append-only batches and per-line origins. The source uniqueness key includes file content hash, sheet and row, preventing renamed identical documents or repeated extraction from bypassing reuse detection. Triggers verify extraction/document/locator/cell consistency, creation transaction and actor, full row coverage and one source batch per imported entry. Journal traces expose origins, and newly created journal-report manifests freeze them under the manifest hash.

Amount parsing preserves all source precision through toman-to-rial conversion. A shared coefficient/exponent check also strengthens bounded journal, financial-statement and inventory values against fractional tails that previously passed nominal constraints after normalization. Valid values retain their prior serialization.

All 21 focused tests passed against PostgreSQL, with CSV and XLSX parser subprocesses. Coverage includes preview, multi-voucher imports, rollback, concurrent retries, duplicate row/file detection, source tampering, tenant and role boundaries, journal/report lineage and direct SQL constraint attacks. See [validation](../research/VALIDATION.md) for the full-suite result and the local database recovery incident. Ruff and Git whitespace results are recorded there.

The [contract](../research/JOURNAL_IMPORTS.md) documents the four routes, explicit mapping example and correction workflow. PDF/OCR table inference, repeated-account aggregation, semantic duplicate detection, statutory filings, real engine quality and full capacity/restore validation remain outside this checkpoint. UI expansion remains deferred. Graphify is local static navigation tooling; its token savings are unmeasured.
