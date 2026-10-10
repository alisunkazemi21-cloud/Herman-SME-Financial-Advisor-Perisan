# Journal imports checkpoint — 2026-10-11

Added explicit CSV/XLSX-to-journal mapping with read-only preview, atomic proposal creation, whole-voucher selection, exact currency/date conversion and immutable per-line extraction provenance. Migration 012 blocks source-row reuse across identical uploads and re-extraction, seals origins to entry creation and preserves tenant isolation. New report manifests include the saved import lineage. Human review is still required before financial posting and report use.

Milestone **C10** in the [development map](../../research/PROGRESS.md). The focused PostgreSQL suite passed all 21 tests; the full suite passed **195**, with one real-OCR fixture skip. Full regression evidence and operational recovery notes are recorded in [validation](../../research/VALIDATION.md). All documents were synthetic; no customer data, real OCR or live model inference was used.

Synchronized artifacts: [contract](../../research/JOURNAL_IMPORTS.md), [chapter](../../research/CHAPTERS/journal-imports-2026-10-11.md), [technical report](../../reports/journal-imports-2026-10-11_technical.md), [narrative](../../media/journal-imports-2026-10-11.md). The existing Marimo prototype remains unchanged under the user's UI deferral. Graphify's code-only index and report were refreshed locally; no graph artifacts or runtime credentials are committed.
