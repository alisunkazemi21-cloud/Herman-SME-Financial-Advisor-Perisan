# C16 public catalog workflow: technical report

Code `f877b9b0ee782caec53bfa3792e7453e94af187f` adds published dated label selection and a typed versioned manifest to analysis/freshness, with selected evidence-byte verification and stable legacy comparison. Label rows count against existing row/byte bounds. Catalog navigation defaults to server time or an explicit aware instant; analysis uses the closing/reporting instant. Original identities, units/modes, imported aliases and saved receipts remain unchanged.

Authenticated public routes expose current/history/detail, proposals/decisions and historical binding review. Role/source/RLS/idempotency controls reuse existing schema 18. Natural-key capture handles concurrent reuse. Exact Decimal strings, no-store and redacted validation protect the API contract; the scoped pure ASGI header wrapper leaves existing parser/cancellation behavior intact.

Scoped lead suites passed 51 joint and four final cases. Exact-code Linux CI passed **543 tests / two skips / 15 warnings / 105.34 seconds**, plus Ruff and Marimo. Full Windows regression passed **544 tests / one real-OCR skip / five warnings / 777.37 seconds**. Review's standalone historical-use presentation gap was repaired and source closure confirmed. Graphify: 1,751 nodes, 5,778 edges, 113 communities, code-only. [Run record and acceptance matrix](../runs/catalog-workflow-2026-10-26/README.md) distinguish worker fixture failures, corrected runs, ownership and final same-code local evidence.

No production-readiness, statutory compliance, real-model/OCR accuracy, full 1,000-business workload, recovery or customer-value claim follows from this scoped backend workflow.
