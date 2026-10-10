# Journal reports checkpoint — 2026-10-10

Added reviewed account mappings, immutable report receipts, five journal-derived portfolio indicators, journal-level cash-flow data, stale-report detection, approved replacement chains and bounded advisor/case retrieval. Migrations 010 and 011 preserve tenant RLS, reviewer roles and append-only records.

The focused report/advisor/case suite passed 39 tests. The full PostgreSQL-enabled suite passed 174 tests with one real OCR test skipped; Ruff and whitespace checks passed. Details are recorded in [validation](../../research/VALIDATION.md). Test inputs and model replies were synthetic; no customer documents or cloud inference were used.

Synchronized artifacts: [contract](../../research/JOURNAL_REPORTS.md), [chapter](../../research/CHAPTERS/journal-reports-2026-10-10.md), [technical report](../../reports/journal-reports-2026-10-10_technical.md), [narrative](../../media/journal-reports-2026-10-10.md). The Marimo prototype is unchanged because the user deferred interface expansion.
