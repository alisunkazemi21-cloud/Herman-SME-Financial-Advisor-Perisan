# Validation history

## Initial prototype — 2026-10-05

- 54 tests passed; the real OCR test skipped because three labeled reference images were unavailable.
- Ratio-module line coverage was 100% across 56 statements. This was not whole-project coverage.
- Ruff and Marimo checks passed; HTML export and browser display of ratios/charts were inspected.
- The Persian profit search showed the two margin ratios. The forecast slider moved from 3 to 4 months and back to 3.
- A synthetic run produced a manifest, README, research chapter, technical report and narrative with one run ID.
- Checks covered changed evidence, ledger tampering, concurrency, reversals, rejection of agent approvals, floating-point monetary inputs, invalid dates, benchmark rates and mixed PDFs.
- Tesseract CLI and Ollama were not found on PATH. Mocked OCR adapters and Ollama transport tests did not establish real-engine quality.
- The sandbox could not read global Marimo settings; the app ran with defaults. Two Windows temporary-directory cleanup warnings did not fail the tests.

No real-document production run occurred. Real OCR evidence, official accounting-standard versions and local-model evaluation remained prerequisites.

## Prototype audit follow-up

58 tests passed and one real OCR test skipped. Added checks covered ambiguous invoice units, multiple candidate amounts, preservation of evidence text, absent time series before advice, Persian journal explanations and synchronized daily/benchmark reports. Ruff and Marimo checks passed.

## Backend checkpoints

| Checkpoint | Local result | Evidence |
|---|---|---|
| Multi-business inventory backend | 86 passed, 1 skipped | [Backend acceptance](BACKEND_ACCEPTANCE.md) |
| Durable extraction queue | 93 passed, 1 skipped | [Queue contract](DOCUMENT_QUEUE.md) |
| Imports, provenance and duplicate review | 108 passed, 1 skipped | [Import contract](TABULAR_IMPORTS.md) |

The skip remains the real OCR engine/reference-fixture test. A FastAPI test-client deprecation warning did not fail the backend checks. The 1,000-business synthetic read benchmark has a narrower scope than full application or OCR capacity; see the raw reports linked from backend acceptance.

## English documentation and typography checkpoint — 2026-10-06

Translated repository prose and archived Markdown reports into English. Future Markdown uses the same stored results through `src/reporting.py`; Persian app messages and source data remain intact. All 13 tracked JSON/evidence files in the pre-change hash inventory remained byte-identical, including manifests, inputs, sample data, benchmarks and the latest pointer.

Validation: 108 tests passed, one real OCR fixture test skipped; Ruff and the Marimo notebook check passed. Local warnings concerned the test client's dependency deprecation, Windows temporary-directory cleanup and inaccessible user-level Marimo configuration; no test failed. No OCR accuracy or new capacity claim is made.

Kalameh is now the preferred dashboard/chart font, using an installed copy when available. The user has no webfont files, so the bundled Vazirmatn/Tahoma fallback remains necessary; Kalameh rendering has not been visually verified. The user-requested `npx vibefarsi add contour` is recorded for a later UI checkpoint and was not executed in this backend/documentation checkpoint.

## Graphify checkpoint — 2026-10-08

Pinned local Graphify/SQL setup, code-only graph build, bounded workflow query, path query, HTML/report generation and excluded-path checks passed. See [verification and limits](GRAPHIFY.md). No application behavior changed; token savings remain unmeasured.

## Advisor context and portfolio checkpoint — 2026-10-08

The full PostgreSQL-enabled suite passed 122 tests; one real OCR test remained skipped. Fourteen new tests cover review gates, validity boundaries, conflicts, idempotent concurrent proposals, role enforcement, tenant isolation, evidence tampering, immutable decisions, read-only context, Quick isolation, output bounds, exact financial formulas, portfolio pagination and API behavior. After the final boolean response-type correction, its portfolio acceptance test passed again. Ruff and whitespace checks passed. Local warnings concern the test-client dependency and Windows temporary-directory cleanup; no application test failed in the final full run.

Graphify's local code-only index was refreshed. No model-quality, OCR-accuracy or full portfolio capacity claim is made. Screen rendering remains deferred by the user. See [the API and metric contract](ADVISOR_PORTFOLIO.md).

## Local advisor draft checkpoint — 2026-10-08

Full PostgreSQL-enabled suite: 135 passed, one real OCR test skipped. After adding explicit financial context selection, all 19 advisor-context/draft tests passed again, including the newly added financial-draft case. Ruff, CLI help and whitespace checks passed. Graphify was refreshed. The preceding portfolio commit also passed GitHub CI (run 37758175132).

Tests cover malformed/partial/oversized/tool-call model responses, input limits before network access, authenticated scope before inference, context receipts, Quick's lack of scoped database reads, generic model failure responses, slot release and concurrent-capacity rejection. Stubbed model results verify software behavior only. The local Ollama API was unavailable and no Ollama executable was found on PATH; live model evaluation is not completed. No model download or user-data inference occurred.
