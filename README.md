# Herman SME Financial Advisor ( Perisan)

A local-first financial advisor for Iranian small businesses. Agents propose, typed Python calculates, and people approve.

The current priority is the multi-business backend. Interface development is paused. Documentation and generated Markdown use English; app text, Persian business data, RTL presentation and evidence retain their original language.

## Backend workflow

Business profile → evidence upload → extraction job → explicit CSV/XLSX mapping → proposed records → human review → inventory reconciliation with traceable inputs.

- [Backend setup, API and acceptance evidence](research/BACKEND_ACCEPTANCE.md)
- [Document queue and worker operations](research/DOCUMENT_QUEUE.md)
- [Tabular imports, provenance and duplicate review](research/TABULAR_IMPORTS.md)
- [Architecture](research/BACKEND_WORKFLOW.md), [metric contracts](research/METRICS_CATALOG.md), [requirements audit](research/REQUIREMENTS_AUDIT.md)

The latest functional checkpoint passed 108 tests; the real OCR fixture test remains skipped. This is an implemented backend foundation, not a completed conversational advisor or a production-capacity certification.

## Installation

Use Python 3.11 or newer. Run these commands from the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,ocr,backend]"
.\.venv\Scripts\python.exe -m pytest tests -q --tb=short
```

Alternatively:

```sh
uv sync --extra dev --extra ocr --extra backend
uv run pytest tests/ -q --tb=short
```

PostgreSQL acceptance tests require `HERMAN_TEST_ADMIN_DSN` pointing to a disposable database; they skip without it. Follow the backend setup guide for the separate migration and restricted runtime roles. Do not serve requests with an administrative database connection.

## Earlier local analysis prototype

The earlier prototype remains available for synthetic demonstrations:

```sh
advisor demo
marimo run src/dashboard/notebook.py --watch
```

The demo is entirely synthetic. Amounts are IRR; it contains no live dollar/gold quotes or purchase recommendations. `marimo edit src/dashboard/notebook.py --watch` opens the reactive notebook editor. Vazirmatn v33.003 is bundled with its OFL license; the app does not fetch a font from a CDN.

The local CLI workflow is:

```sh
advisor ingest invoice.pdf --output extracted.json --engine tesseract
advisor propose proposal.json --book data/book.jsonl
advisor trace J1 --book data/book.jsonl
advisor decide decision.json --book data/book.jsonl
advisor run reviewed_input.json --output data/analysis
advisor advise reviewed_input.json --model mshojaei77/gemma3persian
```

Review extracted text, values, dates, units and accounts before constructing a `JevEntry`. `samples/proposal.example.json` and `samples/decision.example.json` are templates; replace evidence paths and hashes with your own. A local approval needs a `human:...` actor and `reviewed_values: true`. Confidence below 0.8 adds a warning; higher confidence still does not authorize posting. Export Google Sheets to CSV/XLSX; there is no live Sheets connection.

For financial analysis, prepare reviewed `RunInput` using `samples/demo_input.json` as a structural example. The input statement is explicit: journal balances alone do not supply all classifications or opening/closing averages. Every amount carries evidence and a locator. This tool analyzes the supplied statement; it does not claim to prepare statutory statements automatically.

Each successful run writes an input snapshot, evidence archive, manifest, run README, research chapter, technical report and narrative. The dashboard reads the manifest referenced by `runs/latest.json`. Run IDs tie the outputs together. Keep real files and results in ignored `data/` paths, not Git. Historical `_fa.md` filenames remain for link compatibility; their documentation prose is now English.

## OCR and local language model

Install Tesseract separately with `fas` and `eng` language files and put its executable on PATH. Installing the Python wrapper does not install the engine. EasyOCR is optional (`pip install -e '.[easyocr]'`); preinstall local models because automatic downloads are disabled. Aspose and DocFlow were research comparisons, not implemented adapters.

`FinancialAgent` uses a configurable local Ollama model; `mshojaei77/gemma3persian` is the documented example. The client accepts explicit loopback endpoints and disables proxies and redirects. There is no cloud adapter, and Ollama itself must be configured for local inference. The model has no posting or approval tools. Its text is always an unapproved draft; deterministic calculations run without Ollama.

## Financial controls and limits

- Ten ratios use Decimal with input provenance. ROA/ROE use opening/closing averages; nonpositive denominators yield an undefined result.
- The earlier JSONL ledger uses append-only proposals/decisions, locks, a SHA-256 chain and archived evidence. Corrections use reversals. It assumes one trusted local user; its actor string is not enterprise authentication, and a hash chain alone cannot stop a device administrator from replacing the whole file.
- XIRR uses ACT/365F; ambiguous multiple-sign-change cash flows are rejected. USD/18-karat-gold comparisons require dated, evidence-backed rates.
- Forecasts require at least 24 consecutive months. ADF and lag-12 screening precede interpretation. Bootstrap intervals do not guarantee coverage or separately model inflation, shocks or Ramadan.
- Iranian standards 16/39/43 are accountant-review flags, not a claim of full compliance, consolidation or automated revenue recognition.
- PDF extraction applies OCR to pages without text. Partially extracted text in mixed PDFs still needs review. Text/Excel confidence measures transfer, not accounting correctness.

## Real-engine checkpoint

Set `PFA_OCR_FIXTURES` to a directory containing at least three labeled invoices and `cases.json`. Each case needs `image` and `expected_fragments` using normalized Latin digits. `test_real_ocr_three_labelled_invoices` skips without these fixtures. Mocked adapter tests do not establish OCR accuracy; the real-engine checkpoint and accounting review remain required before production use.

Research and decisions: [literature](research/LITERATURE.md), [decisions](research/DECISIONS.md), [workflow](research/WORKFLOW.md).

## Future UI preferences

Use Kalameh for Persian typography; its webfont files are pending, so the prototype prefers an installed Kalameh font with the existing fallback. At the next UI checkpoint, inspect the package and project, then use `npx vibefarsi add contour`. Backend work remains the priority.

## Workflow inspection

[Graphify setup and bounded queries](research/GRAPHIFY.md) provide a local code graph for navigating backend workflows. Refresh it at code checkpoints; graph relationships are not live job telemetry or financial evidence.

## Business knowledge and portfolio

[Advisor context and portfolio API](research/ADVISOR_PORTFOLIO.md) provides reviewed knowledge, isolated Quick context, business highlights, five financial indicators and cash-flow waterfall data. Financial values require reviewed, evidenced inputs; the visible portfolio screen remains deferred.

The backend can optionally generate Persian drafts from reviewed context: start `python -m src.backend.cli serve --advisor-model <installed-model>` with the existing runtime database configuration. See [draft routes and limitations](research/ADVISOR_PORTFOLIO.md#opt-in-local-draft-responses). Drafts are unverified and cannot post or approve records.

[Persistent business cases](research/BUSINESS_CASES.md) save ordered questions, context receipts and optional local drafts. Continuations use bounded, explicitly unverified history and fresh reviewed context. Expected turn numbers prevent silent conversation branches; completed retries reuse their saved receipt. Quick retains no conversation history.

[Tenant financial journals](research/JOURNALS.md) add custom accounts, evidenced multi-line entries, human approvals, duplicate review, exact reversals and dated trial balances. Only approved entries affect balances. Financial amounts remain exact decimal strings.

[Reviewed journal reports](research/JOURNAL_REPORTS.md) now connect journals to the portfolio and business advisor through explicit account mappings, saved input receipts and scope review. Reports flag new backdated postings, support reviewed replacements, and expose journal-based cash-flow data and five indicators without silently choosing between conflicting sources.
