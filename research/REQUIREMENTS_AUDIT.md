# Requirements audit

This is a progress record, not a declaration that the whole product is complete.

## Initial prototype and follow-up — 2026-10-05

| Requirement | Evidence and status |
|---|---|
| Research and decisions before code | Research records and initial commit completed; official accounting sources remain unverified. |
| Ten ratios with exact values and provenance | Implemented; the ratio module reached 100% line coverage against independent expected values. |
| CSV/XLSX, PDF and image ingestion | Adapters and tests implemented. Invoice amount candidates with explicit units added in the follow-up; real OCR remains unvalidated. |
| Persian/Arabic digits and Jalali dates | Normalization and invalid-date tests implemented. |
| Append-only ledger, human decisions, reversals | Implemented for a trusted local single-user context. |
| Understandable journal explanation | Follow-up generates Persian trace text from account labels and recorded values. |
| Iranian standards 16/39/43 | Review flags only; complete accounting rules and compliance are not implemented. |
| Local Ollama drafts without write tools | Adapter and transport tests implemented; real-model evaluation remains open. |
| Uncertainty before advice | Follow-up aligned `advise` with ratio, ADF/seasonality, interval and benchmark context; missing series are explicit. |
| Forecast diagnostics and intervals | Implemented; Ramadan is not modeled separately. |
| USD/gold benchmarks | Evidence-backed calculations and report/dashboard display implemented; no live-rate claim. |
| Synchronized outputs | Shared manifest, unique run artifacts and daily index views implemented. |
| Persian RTL dashboard | Browser-checked prototype with bundled Vazirmatn, search and horizon slider. Further interface work is deferred. |
| Three real OCR reference cases | Still missing; mocked checks do not establish OCR accuracy. |
| Incremental Git/GitHub history | The user created the public repository; local history was merged with its initial commit and pushed. |

## Approved backend milestones

Profiles/memberships, a restricted PostgreSQL runtime role, RLS, immutable evidence, proposals/decisions, catalog/warehouses/recipes/movements/fulfillments and persisted inventory reconciliation are implemented. Quick currently provides request-only calculation, not a complete conversational agent. See [backend acceptance](BACKEND_ACCEPTANCE.md) for boundaries and the synthetic read benchmark.

On 2026-10-06, the durable queue added leases, retries, recovery after worker interruption, immutable extraction output and transition audit events. Validation: 93 passed, one real OCR test skipped. See [queue contract](DOCUMENT_QUEUE.md).

The next checkpoint added atomic CSV/XLSX mapping to count/movement/fulfillment proposals, extraction provenance in analyses, source-row uniqueness, identical-file and matching-event detection, and explicit duplicate-review decisions. Validation: 108 passed, one real OCR test skipped. See [import and duplicate-detection contract](TABULAR_IMPORTS.md).

Still outstanding: conversational agents and verified memory; full tenant-scoped financial journals; semantic invoice/amount matching; corrections to confirmed records; real OCR/model evaluation; official standards; backup/restore and full application capacity validation.

## Documentation language — 2026-10-06

The user requested English documentation at every checkpoint. Repository prose and generated Markdown are being translated; app language and source data remain Persian. This changes presentation, not financial values, stored evidence or previous test results.

## Advisor and portfolio checkpoint — 2026-10-08

Added reviewed business knowledge, bounded read-only business context, request-only Quick context, authorized-business portfolio summaries, reviewed financial snapshots and Decimal cash-flow/five-indicator payloads. The user selected backend data now and screen later. Conversational orchestration and evaluated model answers remain outstanding. See [contract and limitations](ADVISOR_PORTFOLIO.md).

## Local draft integration — 2026-10-08

Business and Quick contexts now connect to an opt-in local Ollama draft route. Context receipts, output bounds and per-process inference limits are implemented. Review/ledger tools remain unavailable to the model. Financial portfolio indicators can be explicitly included in business context. Live Ollama was unavailable; real response-quality evaluation and conversational case history remain open.

## Business cases — 2026-10-09

Persistent case history is now implemented with tenant isolation, immutable ordered turns, bounded non-authoritative history, exact context receipts, retry reuse and stale-continuation rejection. Quick remains stateless. See [case contract](BUSINESS_CASES.md). Real model evaluation, full tenant financial journals, reviewed corrections, semantic invoice matching, real OCR, accounting standards verification and full application capacity/restore testing remain outstanding.
