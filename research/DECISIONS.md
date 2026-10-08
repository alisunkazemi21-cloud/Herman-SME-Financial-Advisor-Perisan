# Decisions recorded before implementation

Initial record: 2026-10-05, after LITERATURE.md and before implementation. Later sections record subsequent approved checkpoints, not claims of complete product readiness.

|Topic|Decision and rationale|Alternative or limitation|
|---|---|---|
|OCR|Tesseract default; optional lazy EasyOCR without automatic downloads; review outputs.|Aspose needs cloud access; DocFlow lacks independent project evaluation. Handwriting and poor scans need human review.|
|Original ledger|Append-only JSONL, process locks, SHA-256 chain, fsync, separate proposal/decision events and hashed evidence.|SQLite scales better. A local administrator can rewrite a chain without an externally trusted root.|
|Approval|A proposal's approved=true is insufficient: require a human actor, reason and text-review confirmation.|Original local identity assumes one trusted user, not enterprise authentication.|
|Corrections|Approved reversal linked to the original; no direct edit or deletion.|Reversals also require review.|
|LLM|Direct loopback Ollama; draft text only, no cloud or action tools.|LangChain adds unnecessary complexity for one endpoint; reconsider for complex workflows.|
|Calculations|Decimal, Pydantic, ten ratios and input provenance.|No NumPy/my727finance for core ratios; floats only for explicitly estimated statistics.|
|Currency|IRR ledger; explicit exact IRT conversion; dated evidence and units for rates.|No default live rates. Dollar/18-karat gold scenarios are not investment recommendations.|
|Dates|jdatetime, valid calendar dates and explicit Jalali month ordering.|Reject approximate conversion and invalid days.|
|Forecast|24 consecutive months, ADF and lag-12 screening, last-value/seasonal baselines and seeded historical-error bootstrap.|Defer Holt-Winters/ARIMA until rolling-origin evaluation. No coverage guarantee or structural-shock model.|
|Documents|CSV/XLSX, PDF with page-level OCR, images and local Google Sheets exports.|No live Google account connector; never execute spreadsheet formulas.|
|Standards|Sample accounts and review flags for standards 43/39/16.|No full compliance claim without verified official editions.|
|Original interface|Persian RTL Marimo, local Vazirmatn/Tahoma, plus ingestion/review/run CLI.|No separate website or external font URLs. Later font preference appears below.|
|Publication|Unique run directories and manifests, synchronized reports/chapters, latest pointer published last.|Stable historical outputs; later language exception changes narrative only.|
|Validation|Synthetic unit, financial, failure, concurrency and end-to-end tests; opt-in real OCR on three fixtures.|Do not report mock OCR accuracy or production readiness before real-engine validation.|

The originally named skills were unavailable and are not mandatory dependencies of this independent implementation. Record new decisions before related changes.

## Original interface and portability follow-ups

Display four decimal places in the interface while retaining exact manifest values. Use a searchable Persian HTML table and Persian forecast slider. Interactive exploration does not overwrite stored results. The separate advise command drafts Ollama advice from calculated results without writing ledger entries.

The prototype bundled Vazirmatn v33.003 from its official repository under OFL, served locally without a CDN. Store manifest pointers with POSIX separators for Windows/Linux portability. Preserve JSON line endings and archived evidence bytes in Git so hashes remain valid.

## Audit follow-ups

- Give advise the same ratios, stationarity/seasonality diagnostics, intervals and documented benchmarks as run. Report absent series explicitly; never invent conclusions from missing data.
- Extract invoice field candidates with transparent field, amount and explicit-unit rules. Never guess ambiguous units. Defer NER substitution until independently evaluated.
- Construct ledger explanations from account names, amounts and decision status, not model prose; preserve document text separately.
- Daily paths index the latest unique run. Display documented dollar/gold comparisons in reports and dashboard; report missing rates explicitly instead of supplying examples.

## User-directed move to a multi-business backend

Pause interface expansion. BACKEND_WORKFLOW.md and METRICS_CATALOG.md define the new design contracts. Choose PostgreSQL and separate blob storage over a large JSON object per business; reuse Decimal and provenance. Conversation text is not authoritative stock data. Validate real database isolation and load before claiming capacity for 1,000 businesses. Business-profile and Quick modes share tools with separate data scopes.

## Approved first backend stage

Implement the domain core and PostgreSQL migrations first. Use NUMERIC(24,6) quantities and NUMERIC(28,6) money, rejecting excess precision; UUID identifiers, composite tenant foreign keys and timezone-aware timestamps. The reconciliation core is independent of databases and LLMs. Check scoped inputs, reviewed coverage and evidence; report complete/incomplete results. Refunds are not physical returns, consumption must not be counted twice, and count adjustments must not conceal shortages.

Use FastAPI and psycopg with parameterized SQL; no ORM initially. Version schemas and transact migrations. Run test PostgreSQL on loopback without system service changes; ignore runtime binaries and test data in Git. Each milestone needs its own acceptance evidence.

The million-movement experiment showed per-row member_role evaluation (about 150,000 buffer hits for 50,000 movements). Migration 2 preserves tenant equality but moves membership evaluation into a statement-level subquery. Repeat isolation checks and preserve before/after results. Warm-cache comparisons do not prove cold-cache performance.

## Approved document queue

Use PostgreSQL FOR UPDATE SKIP LOCKED without another broker. Operational jobs are mutable; requests, documents and extraction outputs remain fixed, with audited transitions. Workers use specific member/business credentials, never superuser access. Claims/finalization use short READ COMMITTED transactions; financial analyses retain repeatable snapshots. Each claim has a new bounded lease token; expired workers cannot publish. Limit attempts to three; retry transient failures with delay and permanently fail invalid input. Extraction never approves records.

Parse in a timed subprocess with temporary files and a minimal environment without application credentials/DSNs. Retain original document IDs/hashes; do not publish temporary paths. This is not a full security sandbox; hard memory limits and real OCR evaluation remain open.

References: [PostgreSQL queue locking](https://www.postgresql.org/docs/17/sql-select.html#SQL-FOR-UPDATE-SHARE), [Python subprocess timeouts](https://docs.python.org/3/library/subprocess.html).

## Approved imports and duplicate detection

Explicit CSV/XLSX mapping selects sheets/rows and SKU, quantity, unit and timestamp columns. Do not infer item identity, units, timezone or event kind. Import at most 100 rows atomically as proposed counts, movements or fulfillments; one invalid row rolls back the batch. Uniqueness across business/document/sheet/row/record-kind prevents replay even after re-extraction. This is not an amendment workflow. Preserve extraction/mapping provenance with records and analyses. PDF/images and nested recipes still need typed proposals and human review.

At the user's request, flag identical SHA-256 files within the same business without automatic deletion/merging. For operational events compare warehouse, item, kind, exact timestamp and unit-normalized quantity. Equal amounts alone are insufficient. Suspected-duplicate approval needs distinct_event with a reason; same_event requires rejection. Semantic similarity, byte-different OCR duplicates and full supplier/invoice-number matching remain future work.

Full testing exposed long Windows staging filenames. Use a short UUID for staging while keeping full content-hash published filenames and atomic publication.

## English documentation checkpoint and future UI preferences

Translate documentation, research, checkpoint reports, developer prose and generated Markdown narrative into English. Keep Persian application text, source data, business names, manifests and evidence unchanged. Historical narrative may be translated without recalculation; preserve data/evidence bytes and retain originals in Git history. Keep existing filenames for link compatibility.

The user selected Kalameh for Persian typography but has no font files available. Prefer locally installed Kalameh and retain the existing fallback; bundling Kalameh remains pending actual webfont files. Never relabel the Vazirmatn binary as Kalameh.

For later UI checkpoints, the user requested `npx vibefarsi add contour`. When UI work resumes, inspect the package and target project before running that command, then verify Persian RTL and Kalameh typography. Do not scaffold a new interface in this documentation/backend checkpoint.

## Graphify workflow inspection — 2026-10-06

Use Graphify 0.9.77 in an isolated project-local environment, with code-only local AST indexing and bounded queries. Exclude runtime state, credentials and financial evidence. Refresh the graph at code checkpoints; verify graph findings against source and tests. Graphs describe code relationships, not live job status or authoritative financial facts. Token savings must be measured rather than assumed. No background watcher or semantic model backend is enabled by this checkpoint.

## Advisor context and reviewed knowledge — 2026-10-08

Implement a read-only advisor context boundary before a conversational model loop. Knowledge claims have stable IDs, named keys, Persian text, evidence and validity intervals. Proposals and reviewer decisions are append-only with tenant RLS, composite document references and idempotent writes. Pending/rejected/expired claims do not become context facts. Overlapping confirmed claims with different text are surfaced as conflicts, never silently selected. This initial contract does not implement correction/supersession or treat narrative claims as calculation inputs.

Business context retrieves explicitly requested keys and at most one saved analysis in one snapshot. Return provenance and a bounded payload; refuse oversized evidence rather than silently truncate it. Quick context is a pure request-only function without a database/service dependency. Both expose deterministic Persian explanation and limitations; they do not call a model, accept model-selected write operations or persist conversation text. No live model-quality claim is made.

The user requested an overall authorized-business portfolio with knowledge highlights, plus cash-flow diagram data and five financial indicators. The user confirmed backend data now, screen later. Add reviewed financial snapshots with per-field document evidence and separate reviewer decisions. Derive opening/inflow/outflow/closing waterfall data, revenue, net income, net cash flow, current ratio and net margin with Decimal. No snapshot means unavailable values. Multiple confirmed snapshots at the latest eligible period end are a conflict, not an automatic winner. These are user-reviewed inputs, not automatic journal aggregation or bank reconciliation.
