# Business cases checkpoint — 2026-10-09

Added tenant-scoped cases, ordered immutable turns, bounded history retrieval and saved context receipts. Migration 008 adds two RLS-protected tables. Completed retries reuse the saved result; stale continuations and inference failures publish no partial turn.

Nine focused PostgreSQL tests passed. Full-suite verification is recorded in [validation](../../research/VALIDATION.md). Model behavior was stubbed; no real customer data or cloud inference was used.

Synchronized artifacts: [API contract](../../research/BUSINESS_CASES.md), [research chapter](../../research/CHAPTERS/business-cases-2026-10-09.md), [technical report](../../reports/business-cases-2026-10-09_technical.md), [narrative](../../media/business-cases-2026-10-09.md). The Marimo notebook remains the existing prototype because the user deferred UI work.
