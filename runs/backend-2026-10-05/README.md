# Backend checkpoint — backend-2026-10-05

This engineering checkpoint uses synthetic data, not a customer's financial records.

- Implemented and tested Decimal ingredient/recipe reconciliation with evidence.
- Tested the multi-business API against real PostgreSQL with a restricted role, proposals/approval, idempotency and audit records.
- Full suite: 86 passed, one real OCR test skipped. After final changes, 28 backend/domain tests passed again.
- Read benchmark: 1,000 businesses, one million movements, 25 workers; 1,000 successful reads, no observed unauthorized access.
- After migration 2, p95 was about 1,946 ms, including fresh connections. This synthetic read benchmark is not a full-application SLA.
- The dashboard and latest financial-report pointer were unchanged in this engineering checkpoint.

Contracts and limitations: [acceptance](../../research/BACKEND_ACCEPTANCE.md). Raw results: [baseline](../../research/benchmarks/backend-2026-10-05.json), [optimized](../../research/benchmarks/backend-2026-10-05-optimized.json).

Synchronized outputs: [research chapter](../../research/CHAPTERS/backend-2026-10-05.md), [technical report](../../reports/backend-2026-10-05_technical_fa.md), [summary](../../media/backend-2026-10-05_fa.md). All use the same acceptance evidence and raw results.
