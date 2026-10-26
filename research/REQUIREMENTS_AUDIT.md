# Requirements audit

This is a progress record, not a declaration that the whole product is complete.

## Latest accepted scope — October 26

C16 compatible catalog review is accepted at `f877b9b`: published dated labels, human-reviewed item/pack revisions, historical-use capture/resolution and consistent analysis/freshness/duplicate behavior are available through authenticated APIs. Full Windows regression passed 544 / one real-OCR skip; exact-code Linux CI passed 543 / two skips, plus Ruff/Marimo. [Acceptance mapping](../runs/catalog-workflow-2026-10-26/README.md#acceptance-mapping) and [API contract](CATALOG_API.md). Prior source/import/analysis/case history remains unchanged.

Next planned scope is C17 category completeness and reviewed follow-up actions. Pricing remains designed, with no new calculation/UI claim. The original broader advisor goal, actual model/OCR quality, accounting depth/official standards, coordinated restore, a complete 1,000-business workload, minimal Persian owner workflow and permissioned pilot/recurring-value evidence remain open. No overall product-completion claim is made.

## Historical October 25 active extensions

- Historical pack-binding storage/review: migration 18 and internal services locally validated by 68 affected PostgreSQL tests and eight readiness unit checks. Analysis/freshness/duplicate integration remains open; publication/full CI are pending after automatic approval-review timeouts. [Evidence](../runs/pack-bindings-2026-10-25/README.md).
- Dashboard pricing: the new [contract](PRICING.md) covers cost determination, competitor/customer evidence, desired margin and profitable/key products and operations. Status is designed, not implemented. Pricing effectiveness requires actual permissioned data and observed decisions/outcomes.

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

At that checkpoint, outstanding work included conversational agents and verified memory, tenant-scoped financial journals, semantic invoice/amount matching, corrections to confirmed records, real OCR/model evaluation, official standards, backup/restore and full application capacity validation. Later sections record progress against these gaps.

## Documentation language — 2026-10-06

The user requested English documentation at every checkpoint. Repository prose and generated Markdown are being translated; app language and source data remain Persian. This changes presentation, not financial values, stored evidence or previous test results.

## Advisor and portfolio checkpoint — 2026-10-08

Added reviewed business knowledge, bounded read-only business context, request-only Quick context, authorized-business portfolio summaries, reviewed financial snapshots and Decimal cash-flow/five-indicator payloads. The user selected backend data now and screen later. Conversational orchestration and evaluated model answers remain outstanding. See [contract and limitations](ADVISOR_PORTFOLIO.md).

## Local draft integration — 2026-10-08

Business and Quick contexts now connect to an opt-in local Ollama draft route. Context receipts, output bounds and per-process inference limits are implemented. Review/ledger tools remain unavailable to the model. Financial portfolio indicators can be explicitly included in business context. Live Ollama was unavailable; real response-quality evaluation and conversational case history remain open.

## Business cases — 2026-10-09

Persistent case history is now implemented with tenant isolation, immutable ordered turns, bounded non-authoritative history, exact context receipts, retry reuse and stale-continuation rejection. Quick remains stateless. See [case contract](BUSINESS_CASES.md). Real model evaluation, full tenant financial journals, reviewed corrections, semantic invoice matching, real OCR, accounting standards verification and full application capacity/restore testing remain outstanding.

## Tenant financial journals — 2026-10-10

The PostgreSQL backend now stores evidenced, balanced multi-line journal proposals, authenticated human decisions, custom business accounts, exact reversals and period trial balances. Pattern-based duplicate review protects approval, including concurrent first approvals. See [journal contract](JOURNALS.md). This closes the basic tenant journal/posting gap. Automated journal proposals/import mapping, account-to-statement classification, period closing, journal report receipts and advisor retrieval remain incomplete. Inventory/knowledge corrections, semantic invoice matching, real engines, official standards and full application capacity/restore evidence also remain outstanding.

## Journal report integration — 2026-10-10

Reviewed account mappings, immutable journal report receipts, five derived portfolio indicators, journal-level cash-flow data, freshness detection, reviewed report replacement and bounded advisor/case retrieval are implemented. See [report contract](JOURNAL_REPORTS.md). These are scoped management reports; statutory statements, closing controls, gross bank-flow classification, automatic journal proposals/import mapping and large batch reporting remain incomplete. Inventory/knowledge correction, semantic document matching, real engine evaluation, standards verification and operational capacity/restore gates remain open.

## Extracted journal imports — 2026-10-11

Explicit CSV/XLSX voucher mapping now supports read-only preview, atomic pending journal proposals, exact unit/date conversion, source-row reuse prevention across identical files/extractions, immutable row lineage and provenance in new report receipts. See [import contract](JOURNAL_IMPORTS.md) and [validation](VALIDATION.md). This closes the structured journal-import gap, while account inference and PDF/OCR table mapping remain incomplete. Decimal precision validation also rejects tiny fractional tails independently of arithmetic context.

Remaining work includes a general financial Quick advisor beyond the current inventory request, inventory/knowledge correction, broader semantic document matching, actual local-model/OCR evaluation, official standards verification, closing controls, gross bank-flow classification, large batch reporting, operational backup/restore and full application capacity. The user continues to defer interface expansion; the existing prototype is not the completed business portfolio screen.

## General Quick Advisor — 2026-10-11

Quick now accepts questions without inventory, optional request-local text excerpts and partial financial figures. The shared ten-ratio definitions and two cash calculations provide values with per-input source references, or explicit missing/undefined status. A separate Quick prompt supports general explanations without giving the model calculation/posting tools. Authentication remains required; business/history retrieval and conversation persistence are excluded. See [contract](QUICK_ADVISOR.md) and [validation](VALIDATION.md).

This closes the mandatory-inventory restriction and the general request/typed-finance context gap. Real-model answer quality, stateless binary document ingestion, inferred financial extraction, reviewed knowledge/inventory corrections, semantic matching, official standards, operational restore/capacity and the deferred product UI remain incomplete.

## Reviewed knowledge corrections — C12, 2026-10-11

Explicit same-key whole-claim replacements preserve original claims and decisions, require human approval, arbitrate concurrent reviewers, update fresh advisor context/portfolio highlights, and retain exact saved case receipts. Paginated lifecycle/history reads expose pending and superseded claims. See [correction semantics](KNOWLEDGE_CORRECTIONS.md). Focused checks passed; the full PostgreSQL suite passed **250 tests**, with **one real-OCR skip**; Ruff and whitespace checks passed.

Inventory/catalog corrections, semantic matching, stateless binary Quick intake, real model/OCR evaluation, official standards, closing controls, gross bank flows, large reporting batches, restore/capacity and the deferred visible portfolio remain incomplete. No application-completion or production-readiness claim is made.

## Reviewed inventory corrections — C13, 2026-10-11

Counts, movements, recipes and fulfillments now support reviewed whole-record correction, with concurrent-successor constraints, explicit current-count selection, independent duplicate review and preserved source-row reservations. New reconciliation stores correction/import ancestry without changing previous receipts. Creation-transaction sealing protects recipe lines and origin metadata; recipe-yield precision cannot silently round on persistence. See [the contract](INVENTORY_CORRECTIONS.md). Focused checks passed; the full PostgreSQL suite passed **277 tests**, including all 27 new correction cases, with **one real-OCR skip**. Ruff and whitespace checks passed; the final record-detail no-store and exact-decimal response adjustments passed two focused API/backend tests in 8.87 seconds.

Inventory-analysis freshness/impact and catalog/unit correction remain open, alongside semantic document matching, binary Quick intake, real OCR/model acceptance, official accounting rules, closing/reporting depth, operational restore/capacity and the deferred visible portfolio. The overall goal is not complete.

## Inventory freshness and impact — C14, 2026-10-11

Shared input selection and bounded typed comparison now expose current/stale/unknown states in analysis reads, portfolio previews and advisor context. Change references and explicit count replacement requirements do not alter earlier receipts or calculate an unreviewed new answer. Fresh contexts withhold stale/unknown numeric results and provenance; saved contexts remain exact. The final focused suite passed **36 tests** in 129.54 seconds; the final full PostgreSQL suite passed **313 tests**, with **one real-OCR skip**, and Ruff passed. See [the contract](INVENTORY_FRESHNESS.md).

The next intended backend checkpoint is stateless binary document intake for Quick Advisor, extending its text/figure-only input path. Catalog/unit correction, semantic document mapping/duplicates, real OCR/model acceptance, accounting/closing/reporting depth, operational restore/capacity and the deferred owner interface remain incomplete. Current input equality is not an integrity or completeness certification. The complete application goal remains open.

## Stateless Quick document intake — C15, 2026-10-12

Quick accepts temporary CSV/XLSX, PDF and supported image uploads without business records or history. Bounded source packing preserves hashes and page/row/image locations; calculations still require typed inputs. Handled Quick responses/errors are no-store, validation does not echo source content, credentials are rechecked and parser descendants/files are cleaned up. See the [contract](QUICK_DOCUMENTS.md) and [validation](VALIDATION.md).

The full PostgreSQL run passed 362 tests with one real-OCR skip. After the final locator-whitespace fix and added case, 86 focused Quick tests passed, including all 50 intake cases. No migration is needed. This closes bounded stateless document intake, not semantic financial understanding or real OCR/model quality. Catalog/unit correction, accounting/closing/reporting depth, restore/full workload capacity and the deferred owner interface remain open.
