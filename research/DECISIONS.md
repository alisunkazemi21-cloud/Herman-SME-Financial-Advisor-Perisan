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

## Local draft response integration — 2026-10-08

Connect reviewed context to the existing loopback Ollama adapter through opt-in server configuration. Business and Quick draft routes build their own typed context; callers cannot supply arbitrary retrieved context or choose tools/endpoints/models. Return the exact context and its SHA-256 beside an explicitly unverified Persian draft. No conversation persistence, model tool calls, posting or approval is introduced. Limit concurrent inference to one request per application process, bound input/output, and map timeout/malformed/unavailable model responses to a generic 503 without leaking transport details. Live model quality remains a separate validation gate.

## Persistent business cases — 2026-10-09

Add tenant-scoped append-only cases and ordered turns. A turn stores the typed request, exact context receipt and draft (or an explicitly requested deterministic context-only response). Historical text is bounded, labeled non-authoritative and never promoted to reviewed knowledge or numeric inputs. Quick has no case/history API.

Use caller-supplied expected turn number with a unique business/case/turn constraint to reject stale concurrent continuations. Idempotency hashes the typed request, not nondeterministic model output; retries return the stored turn without repeating inference. Read and write roles are checked before context/model work and again at publication. Inference runs outside database transactions. Failure publishes no partial turn. Past context receipts remain immutable even when current knowledge changes. No model receives a database, write or approval tool.

Completed retries avoid inference; concurrent requests may both infer before a single publication wins. This is a publication guarantee, not exactly-once model execution. Recheck the API credential after generation and membership at publication; these checks do not make credential revocation atomic with publication.

## Tenant financial journals — 2026-10-09

Extend the PostgreSQL backend with an immutable per-business account catalog, multi-line IRR journals, reviewer decisions, exact full reversals and a period trial balance. Keep the earlier JSONL prototype separate; do not copy its trusted actor strings into HTTP authentication. Each of 2–100 distinct-account lines has a positive exact amount, debit/credit side and tenant-scoped document/locator. Validate Gregorian/Jalali agreement and equal totals with Decimal and deferred database constraints. Stamp journal creation transactions in a trigger and allow line inserts only within that transaction; otherwise append-only headers alone would still allow later mutation through extra lines.

Only owner/reviewer decisions marked reviewed-values authorize posting. Detect exact accounting-pattern duplicates (date/currency/account/side/amount) independently of descriptions and evidence names; approval of a repeated pattern requires an explicit distinct-event decision. A partial unique index protects simultaneous approvals. Reversals are server-generated exact inverse lines, cannot predate the original, and at most one reversal may be approved per original. Rejected reversal proposals do not prevent a new proposal. Corrections consist of a reviewed reversal plus a separately reviewed replacement.

Trial balances aggregate only approved entries, preserving debit/credit directions, opening balances and dated movements as exact strings. Verify distinct source files before returning values, with explicit account/document bounds instead of silent partial totals. Do not derive statutory statements or cash-flow classifications automatically from account labels. This is an accounting storage/calculation contract, not newly verified compliance with Iranian standards.

## Journal reports, mapping and advisor retrieval — 2026-10-10

Introduce immutable, evidenced account mappings with separate reviewer approval. Classify every currently defined account explicitly as current cash, other current asset, noncurrent asset, current/noncurrent liability, equity, revenue or expense. Validate category compatibility against the account kind. A new account requires a new complete mapping for future reports; do not silently infer classification from labels.

Create bounded immutable report receipts from approved journals in one database snapshot. Preserve the exact source lines, approvals, mapping and source hashes in an input manifest, hash the manifest and result, and compute the seven portfolio constants plus trial balances with Decimal. Cash movement is netted within each journal across mapped cash accounts; internal transfers cancel. Inflow/outflow are the sums of positive/negative journal cash nets, not a claim of gross bank receipts/payments. Ledger revenue/expense movements are not statutory profit if closing entries or incomplete postings are included. Require a reviewer to confirm report scope and review values before portfolio/advisor use.

Reports remain historical receipts when new backdated approvals arrive. Compare the saved source-entry set to current approved entries through the report end date; stale reports cannot supply default portfolio values. Select an approved report explicitly for bounded advisor context, including freshness and provenance. Preserve pending/rejected report isolation and Quick's stateless boundary. Treat equally recent approved statement and journal reports as a conflict. Scope: at most 1,000 accounts, 10,000 lines and an 8 MiB manifest; fail rather than truncate. Statutory statements, closing-period controls, gross bank cash-flow classification and large batch reports remain separate requirements.

Support explicit report supersession so a refreshed report can replace a stale approved receipt for the same period without leaving the portfolio permanently conflicted. The replacement requires its own scope review; only one replacement may be approved for each predecessor. Preserve both receipts, exclude superseded reports from default selection, and return a superseded status for an explicitly selected old receipt. Unlinked reports remain conflicts. Apply this refinement as migration 011 after the already-tested migration 010.

## Extracted table to journal proposals — 2026-10-10

Add explicit CSV/XLSX long-form journal mapping: voucher key, account code, debit, credit, date and description columns, plus an explicit Gregorian/Jalali date convention and IRR/IRT amount unit. Preserve normalized source cells and extraction/parser identity. Convert toman to rial with a sufficient Decimal context before validating amount precision; never round oversized source values into acceptance. Each source row becomes one journal line, so repeated accounts within a voucher are rejected under the existing distinct-account journal contract rather than silently aggregated.

Import whole selected vouchers, including every row for their keys on the chosen sheet, and require consistent date/description within each voucher. One invalid voucher rolls back the entire batch. Preserve per-line source rows with same-business foreign keys, document/hash/extraction consistency and creation-transaction sealing. Source-row uniqueness uses source bytes hash + sheet + row, so renamed identical uploads and repeated extraction cannot bypass reuse checks. Different source bytes remain subject to the existing accounting-pattern duplicate review. Imported entries always remain proposals; import permission does not authorize posting.

Expose provenance in journal traces and freeze it in newly created report manifests. Keep older receipts unchanged. Synchronous imports accept at most 500 source rows and the existing 100-line journal bound. This path does not guess accounts, units, dates or voucher boundaries, and does not treat PDF/OCR text as a table without a reviewed structural mapping.

The excessive-fraction test exposed context-sensitive Decimal constraint validation: a tiny fractional tail beyond the default precision could pass nominal digit/place limits. Add a shared, tuple-based precision check before those constraints for bounded journal, statement and inventory values. This preserves valid numeric values and their serialization while rejecting hidden fractional tails independently of the active Decimal context.

## Visible project milestones — 2026-10-11

The user requested visual and contextual milestones to trace development. Maintain a repository progress map with stable checkpoint IDs, capability segments, verified evidence, remaining gates and the next intended checkpoint. Show scope-qualified states rather than an invented overall completion percentage. Historical test totals measure regression coverage, not product completion or engine quality. Provide an interactive conversation view of the same snapshot. This is project progress reporting; the user's deferral of the business application interface still applies. Update the progress map with later checkpoints.
