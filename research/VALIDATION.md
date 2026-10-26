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

## Persistent business cases — 2026-10-09

Nine focused PostgreSQL tests passed. The final full PostgreSQL-enabled run passed 145 tests with one real OCR fixture test skipped in 179.56 seconds. Ruff and Git whitespace checks passed. The first full run was interrupted after errors and a prolonged stall; PostgreSQL logged an authentication timeout. A fresh connection succeeded, and the fail-fast full rerun passed without restarting PostgreSQL or changing application code. The final run reported 21 warnings; the successful result does not remove the outstanding real-engine validation gates.

Tests cover immutable context receipts, completed retry reuse, bounded history without promotion to knowledge, tenant/role isolation, stale continuations, inference failure, concurrent publication, membership loss, authenticated endpoints and session revocation during inference. Model responses remain stubbed. No live-model quality or full application capacity claim is made.

Graphify code-only extraction and report regeneration completed: 724 nodes, 2,103 relationships and 40 communities. The local report uses structural community names; token savings remain unmeasured. Backend documentation and checkpoint artifacts are synchronized; the Marimo prototype remains unchanged under the user's UI deferral.

## Tenant financial journals — 2026-10-10

Final full PostgreSQL-enabled run: 163 passed, one real OCR fixture test skipped, 23 warnings, in 127.18 seconds. All 18 new journal tests also passed alongside the isolated existing forecast test (19 combined). Ruff and Git whitespace checks passed. An initial full run terminated with a Windows access violation while importing SciPy under timed stack-dump diagnostics; the isolated forecast check and subsequent full run without the timed diagnostic both passed. No dependency changes were made to obtain that result.

Journal tests cover invalid numeric/date inputs, normalized duplicate fingerprints, split entries, reviewer-only posting, immutable traces, exact large Decimal values, concurrent duplicate approval, rejected-reversal retry, exact reversal constraints, date boundaries, source tampering, tenant isolation, direct database constraints, refusal to truncate large reports and API decimal serialization. The PostgreSQL suite exercises migration 009 with restricted runtime roles. No real accounting documents, OCR engine or language model were used.

Graphify code-only extraction and report generation completed with 800 nodes, 2,380 relationships and 53 communities. Generated graphs remain local; token savings are unmeasured. English artifacts are synchronized, and the UI remains deferred. The previous business-case commit 62ec54a passed [GitHub CI](https://github.com/alisunkazemi21-cloud/Herman-SME-Financial-Advisor-Perisan/actions/runs/37986796754); the prior draft commit 9873987 also passed CI. See [the journal contract](JOURNALS.md) for statement mapping, reporting and capacity limits.

## Journal report integration — 2026-10-10

Final full PostgreSQL-enabled suite: 174 passed, one real OCR fixture test skipped, 25 warnings, in 166.90 seconds. The focused report/advisor/case suite passed 39 tests, including 11 new report tests. Ruff and Git whitespace checks passed. Tests applied migrations 010 and 011 and exercised restricted runtime roles. The preceding journal commit 2eb43cd passed [GitHub CI](https://github.com/alisunkazemi21-cloud/Herman-SME-Financial-Advisor-Perisan/actions/runs/38044664362), including fresh-database migration, the full suite, Ruff and Marimo checks.

Coverage includes internal cash transfers, accruals, liabilities, mapping completeness/type checks, empty-ledger refusal, reviewer gates, canonical receipts, idempotent retries, later backdated approvals, immutable historical results, explicit replacement and concurrent branch prevention, competing statement/report sources, source tampering, tenant isolation, database review policy, oversize failure, old case-request serialization and bounded draft context. Model responses and financial inputs were synthetic. Real OCR/model quality, statutory compliance, batch-report performance and complete application capacity remain unverified.

Graphify was refreshed locally with 880 nodes, 2,687 relationships and 48 communities. English contract, run README, chapter, report and narrative are synchronized. The existing Marimo prototype remains unchanged under the user's UI deferral. See [journal report semantics and limits](JOURNAL_REPORTS.md).

## Extracted journal imports — 2026-10-11

Final full PostgreSQL-enabled suite: **195 passed, one real OCR fixture test skipped**, 28 warnings, in 361.87 seconds. All 21 focused import tests passed in 85.17 seconds. Ruff and Git whitespace checks passed. Tests applied migration 012 and exercised restricted runtime roles, real CSV/XLSX parser subprocesses, atomic multi-voucher proposals, whole-group validation, concurrent retry reuse, source-row uniqueness across extraction versions and renamed identical files, source tampering, role/tenant boundaries and lineage in journal/report receipts. Direct SQL tests reject empty batches, late or forged origins, missing line origins and extra lines after an earlier forced constraint check.

An initial fractional-tail check failed and led to coefficient/exponent precision validation for bounded journal, statement and inventory inputs. Regression checks now reject that tail and accept valid maximum values even under a low Decimal precision context. The first database-enabled attempt on October 11 stopped at connection setup because the local cluster was down after an interrupted shutdown. The existing cluster recovered after startup; although the startup wait expired, its live recovery process continued and readiness was confirmed before rerunning tests. The final full run had a temporary output pause, then completed without interruption or restart. No database reset or application workaround was used.

The preceding journal-report commit `4ac9b2f` passed [GitHub CI](https://github.com/alisunkazemi21-cloud/Herman-SME-Financial-Advisor-Perisan/actions/runs/38046003098), including fresh-database migration, full tests, Ruff and Marimo. This checkpoint's local inputs remain synthetic; real OCR/model quality, statutory compliance and full application capacity/restore remain unverified. Warnings did not fail the final run.

Graphify code-only extraction and report generation completed with 948 nodes, 2,969 relationships and 56 communities, using zero model input/output tokens. The bounded 900-token workflow query reported truncation; total token savings remain unmeasured. English contract, run, chapter, report and narrative are synchronized, and a [progress map](PROGRESS.md) now records milestone and segment status. The existing Marimo prototype remains unchanged under the user's UI deferral.

The user-requested conversation progress view was browser-inspected: workstream selection changes the verified/open/evidence details, the milestone tab displays the historical sequence, and selecting C09 shows its report capability and cash-flow limitation. This is a dated project-status view, separate from the deferred product interface. The repository map and checkpoint-update rule are maintained in Git.

## General Quick Advisor — 2026-10-11

Milestone **C11**: the final PostgreSQL-enabled suite passed **226 tests**, with **one real-OCR fixture test skipped**, 30 warnings, in 198.42 seconds. The focused Quick/ratio/advisor/transport suite passed 71 tests, including 31 new Quick cases, in 63.90 seconds. Ruff and Git whitespace checks passed. No database migration was needed. The preceding C10 commit `ec65d41` passed [GitHub CI](https://github.com/alisunkazemi21-cloud/Herman-SME-Financial-Advisor-Perisan/actions/runs/38086183616).

Coverage includes question-only input, untrusted source text/hash preservation, independent expected values for all twelve Quick metrics and the legacy ten-ratio path, exact large toman conversion, fixed Decimal precision/rounding despite ambient context changes, missing figures, undefined denominators, duplicate/source/field/unit/date constraints, partial balance-sheet consistency, raw typed-context and expanded-result limits, authentication, no business transactions during context/draft creation, no cross-request carryover, context receipts and Quick-specific prompt selection without action tools. Existing inventory Quick, business advisor, case, journal and report checks remained green in the full run. The Persian example calculates current ratio 2 and reports missing inputs for quick ratio and net cash flow.

Graphify code-only extraction and report generation completed with 990 nodes, 3,089 relationships and 58 communities. The prompt-text module yielded no AST symbols; graph coverage is partial, no semantic model was used and token savings remain unmeasured. English contract, run README, chapter, technical report, narrative and milestone map are synchronized. The visible product interface remains deferred. Test financial data and model replies are synthetic; live-model quality, actual OCR, statutory interpretation and full operational capacity/restore are not established by this checkpoint.

The dated C11 progress view retains C01–C10 and adds the new milestone. Browser inspection confirmed the updated current/next markers and that selecting C11 displays the new Quick capability and remaining input/model boundaries. This progress view is separate from the deferred product UI.

## Progress presentation refinement — 2026-10-11

Documentation-only update: the root README now shows the last verified C11 checkpoint, the planned C12 checkpoint and the current 226-pass / one-skip result instead of the stale 108-test summary. The maintained progress map adds status definitions and explicit C12 completion criteria. The conversation view adds a next-checkpoint tab, evidence links and the same planned/verified distinction.

Verified the exact C11 commit `4f918ac0d2e652ddf8ed5201479a09fec5f4875f` against [GitHub run 38103570884](https://github.com/alisunkazemi21-cloud/Herman-SME-Financial-Advisor-Perisan/actions/runs/38103570884): completed successfully. Local documentation links, fragment structure and Git whitespace checks passed. Browser inspection verified the next-checkpoint tab and C11 milestone selection. No application code changed and no new application test run or functional checkpoint is claimed.

## Reviewed knowledge corrections — C12, 2026-10-11

The full PostgreSQL suite passed **250 tests**, with **one real-OCR fixture test skipped**, 33 warnings, in 211.78 seconds. The final correction suite passed **24 tests** in 38.29 seconds; an earlier mixed correction/advisor/case run passed 45 before two additional checks. Ruff and whitespace checks passed. Migration 13 applied to the existing local test schema and migration reentry preserved correction history. GitHub CI supplies the separate fresh-schema run.

Coverage includes pending/rejected replacement behavior, full validity-interval correction and boundaries, independent conflicts, matching evidence, 22-record chains before the 20-claim context cap, current-only evidence verification, unchanged financial figures, paginated states/lineage, tenant/role boundaries, API authentication, pre-correction idempotency payloads, concurrent approval with one winner and no failed-write audit/key, direct SQL link forgery/branch prevention, immutable claim/decision rows and exact saved case receipts. No real customer data or model inference was used.

Graphify code-only refresh completed with **1,029 nodes, 3,252 relationships and 52 communities**. Changed communities use their code hubs as labels; no external semantic model was invoked and token savings remain unmeasured. The contract, run README, chapter, report, narrative and progress map are synchronized. The user-deferred product UI remains unchanged. Inventory correction, broader document matching, real engines, statutory review, recovery and full application capacity remain open.

Marimo's unchanged notebook check exited successfully; local user-config discovery emitted access-denied warnings and used its fallback configuration. Browser inspection of the dated progress view confirmed C12 selection, its replacement boundary and the planned C13 tab. The inline view is development tracking, not the deferred business application screen.

## Reviewed inventory corrections — C13, 2026-10-11

The full PostgreSQL suite passed **277 tests**, including **27 new inventory-correction cases**, with **one real-OCR fixture skip**, 36 warnings, in 287.55 seconds. The preceding correction-only run passed 26 in 67.79 seconds before an added import-origin guard case; the earlier correction/backend/import run passed 34. After that full run, the final record-detail no-store and exact-decimal response adjustments passed two focused API/backend tests in 8.87 seconds. The HTTP check preserves `999999999999999999.123456` as a string; a probe of the default encoder demonstrated a lossy float conversion. Ruff and whitespace checks passed. Migration 14 applied to the existing local schema; migration reentry retained replacement history. The preceding C12 commit `3ff6eee` passed [GitHub run 38121290862](https://github.com/alisunkazemi21-cloud/Herman-SME-Financial-Advisor-Perisan/actions/runs/38121290862).

Independent expectations cover corrected closing count (zero shortage), purchase (27 kg shortage), recipe (100 kg usage / 27 kg shortage), fulfillment (108 kg usage / 19 kg shortage), moved-out events, missing recipe coverage and imported purchase lineage (15 kg shortage after an 8 kg revision). Other checks cover pending/rejected candidates, one concurrent approval winner, duplicate ancestry versus independent events, inherited import values and row reuse prevention, current count IDs, idempotency, unchanged earlier analyses, API/RLS boundaries, SQL predecessor forgery, transaction-sealed recipe/origin data and bounded provenance with atomic failure.

A targeted probe showed that the old preparation-yield model accepted a fractional tail beyond six places; the shared context-independent validator now rejects it before database persistence while preserving valid trailing zeros. This fixes input fidelity, not the consumption formula.

The final code-only Graphify refresh recorded **1,093 nodes, 3,504 relationships and 60 communities**. Changed communities use code hubs as labels; no external semantic model was invoked and token savings remain unmeasured. The full test process and two delayed read-only jobs were polled using their existing handles until they completed; none was restarted on an observation timeout. English contract, run, chapter, report, narrative and progress map are synchronized. The Marimo prototype remains unchanged under the user's UI deferral.

Older inventory analyses remain snapshots; freshness/impact reporting is the next planned checkpoint. Catalog corrections, semantic document understanding, real engine quality, authoritative accounting rules, restore/capacity and the visible portfolio remain incomplete. This checkpoint does not establish whole-product completion.

Browser inspection verified the dated C13 progress map: selectable financial workstream, retained C01–C13 history, correction scope and a separate planned C14 tab. Desktop, 360px next-checkpoint and 320px workstream views remained readable without horizontal clipping. All 90 local Markdown link targets checked across the changed checkpoint documents exist. The view tracks development; it does not expand the deferred product interface.

## Inventory freshness and change impact — C14, 2026-10-11

The final PostgreSQL suite passed **313 tests**, including **36 new freshness cases**, with **one real-OCR fixture skip**, 47 warnings, in 543.21 seconds. The final focused suite passed 36 in 129.54 seconds. Ruff and whitespace checks passed. No migration beyond 14 is required. The preceding C13 commit `62b0457` passed [GitHub run 38140612197](https://github.com/alisunkazemi21-cloud/Herman-SME-Financial-Advisor-Perisan/actions/runs/38140612197).

The first mixed run passed 74 and failed one new case-history test: the test omitted `generate_draft=False` while supplying a context-only callback. Correcting the fixture produced a 33-pass focused run. An intermediate full run passed 310 in 408.54 seconds. Final review then added typed result/scope validation and safe unknown summaries for malformed saved results; all 36 focused cases and the final 313-test regression passed. Test processes were polled through their existing handles; none was restarted because observation timed out.

Coverage includes all four approved correction kinds, pending/rejected candidates, moved-in/out records, half-open event/recipe bounds, warehouse isolation, explicit current-count chains, unchanged missing counts, independent proposal/review/rejection effects, conservative catalog/conversion/recipe inputs, equivalent numeric/date/order representations, exact old receipts and retries, sample totals versus truncation, row/byte overflow, hash/format/version/scope failures, API authentication/no-store, and fresh versus saved case contexts. A separate committed write after snapshot acquisition remains invisible within that comparison and is visible in the next read. Recalculation is forbidden during reads. The file-tampering test explicitly confirms the declared boundary: input equality does not reverify bytes.

Graphify code-only extraction and report generation completed with **1,150 nodes, 3,732 relationships and 61 communities**. Changed communities use code-hub labels; coverage is partial/inferred, no semantic model was invoked and token savings remain unmeasured. The contract, run README, chapter, technical report, narrative and progress map are synchronized. The Marimo prototype is unchanged under UI deferral. All financial records and model-related fixtures are synthetic; no real OCR/model-quality or full application-capacity claim follows.

The next planned backend checkpoint is C15 stateless document intake for Quick Advisor. Catalog correction, semantic mapping/duplicates, real engines, official accounting/closing/reporting depth, recovery/capacity and the deferred owner interface remain incomplete. The overall goal remains active.

The dated C14 progress view was browser-checked with its final 313-pass marker, selectable C01–C14 history, six workstreams and planned C15 tab. The 320px preview's document width equaled its scroll width, with readable wrapping and no horizontal overflow; desktop milestone layout was also inspected. The preview server was deliberately refreshed after updating its cached document, then closed after verification. The inline view is development tracking, not a new product screen.

## Current-work tracking refinement — 2026-10-11

Documentation and progress-view update only. The map now distinguishes last-verified C14 from C15 design review, names S2/S4 as the current capability segments, and tracks design, implementation, validation and publication separately. Parser inspection is recorded as preparation; C15 has no implemented or accepted intake contract yet. The README and decision log use the same distinction. Earlier checkpoint evidence remains unchanged.

The public GitHub API confirmed that run **38168599926** completed successfully for the exact C14 SHA **e84304831588f199a05f45bca2731104e7dff980**. The maintained map now links that run and commit directly. The conversation view was browser-inspected: segment selection changes the delivered/open/evidence details, milestone selection exposes C14's behavior and limits, and Current work shows one active design stage with subsequent stages pending. At a 320px viewport, document width and scroll width were both 274px; the stage labels wrapped without horizontal overflow. The temporary viewport and preview tab were cleaned up after inspection.

All 53 local documentation links in the four changed Markdown files passed existence checks. Fragment identifiers, tab targets, six segments and fourteen milestone selectors passed structural checks; Git whitespace checks passed. This change adds no application functionality or new checkpoint and does not claim a fresh local regression run. The prior C14 result remains 313 passed with one real-OCR skip. Product UI remains deferred; the project-progress view is separate.

## Stateless Quick document intake — C15, 2026-10-12

The full PostgreSQL suite passed **362 tests**, with **one real-OCR skip**, 53 warnings, in 421.28 seconds. Final review identified that inherited string trimming could merge locators for distinct sheet names with leading spaces. After preserving locator whitespace and adding that case, the combined Quick/intake/draft suite passed **86 tests**, including all **50 intake cases**, with 51 warnings, in 24.96 seconds. Two targeted reconstruction/whitespace checks also passed in 3.51 seconds. The full run collected the earlier 49-case intake version; the final focused run validates the changed handling. Ruff and whitespace checks passed. No migration is needed.

The first non-database run passed 27 and failed 10: the restricted Windows child lacked home-directory variables, but extraction attempted to resolve an optional model path even for CSV. Moving this lookup to the parent yielded 37 passes and two database skips. The first database-enabled mixed run passed 74 and failed one fixture because it reused `application/octet-stream` for a subsequent JSON request. Correcting that test header yielded 83 passes; two later engine-availability tests produced a 49-pass intake run before the final sheet-name check. Source exceptions, byte payloads and real credentials are not persisted in these artifacts.

Database startup initially failed under the sandbox with Windows restricted-token error 87. An elevated startup wait expired while the existing process continued recovery. Its exact process was then confirmed live and accepting connections on the default port 5432. A deliberate restart changed it to the existing test port 55432, without resetting data, and completed successfully. No restart was triggered merely by an observation timeout; the full regression process was polled through its original handle to completion.

Coverage includes actual local CSV/XLSX/text-PDF subprocesses, supported image and scanned-page adapters with controlled OCR output, full-byte/text hashes, page/row/image reconstruction across chunks, preserved sheet names, copied-origin bounds, formula/array-formula rejection, undersized XLSX dimension metadata, row/cell/archive/page/pixel/text/reference limits, missing OCR executable/Persian pack/EasyOCR weights, actual descendant termination on normal exit and timeout, Windows assignment failure before the start handshake, environment allowlisting, local scratch paths, temporary cleanup, receive timeout/disconnect, cancelled-request slot retention, authenticated no-store responses, credential revocation and no business transactions/blob changes/request carryover. Windows assignment is platform-specific; Linux CI separately exercises POSIX process-group cleanup. No real OCR or model-quality claim follows from controlled adapter replies.

Graphify code-only extraction and report regeneration completed with **1,262 nodes, 4,037 relationships and 77 communities**. Code hubs label communities; coverage remains partial/inferred, no semantic model was used and token savings remain unmeasured. The contract, run README, chapter, report, narrative and progress map are synchronized. The existing Marimo prototype remains unchanged under UI deferral. The preceding tracking commit `e34813259ba65cdf588982f9e4419c818d9d141e` passed [GitHub run 38169623486](https://github.com/alisunkazemi21-cloud/Herman-SME-Financial-Advisor-Perisan/actions/runs/38169623486).

Catalog/unit corrections, semantic financial-document matching, real engine acceptance, official accounting/closing/reporting depth, backup/restore, representative 1,000-business capacity and the visible portfolio remain incomplete. The overall goal remains active.

The dated C15 progress view was browser-inspected in desktop and 320px layouts. C15 milestone selection shows the temporary-source capability and distinguishes the full regression result from final focused checks. Six capability segments retain their open gates; C16 is explicitly planned. At 320px, document width and scroll width were both 274px. All 136 local Markdown links checked in the maintained research/docs and new checkpoint artifacts exist. The temporary viewport and preview tab were reset/closed after inspection.

## C15 Linux descendant cleanup repair — 2026-10-13

The first C15 exact-commit [GitHub run 38216264352](https://github.com/alisunkazemi21-cloud/Herman-SME-Financial-Advisor-Perisan/actions/runs/38216264352) failed `test_process_tree_terminated_on_success_and_timeout[False]`: a spawned child wrote after `run_contained` returned. The cleanup sent SIGKILL to the POSIX process group but only waited for its direct parent. Commit `1589a7e` now waits up to five seconds for all non-zombie members of the group before returning or reporting a cleanup error.

Local Windows intake regression: **47 passed, three skipped** in 26.53 seconds; Ruff and Git whitespace checks passed. The exact-commit Linux [run 38315758134](https://github.com/alisunkazemi21-cloud/Herman-SME-Financial-Advisor-Perisan/actions/runs/38315758134) passed **362 tests, two skipped, five warnings** in 70.01 seconds. Ruff and Marimo checks passed. The Windows-focused run was completed before a read-only tightening of the Linux process scan; Linux CI covered the final commit. This is scoped parser lifecycle evidence, not real-engine or production acceptance.

## C16 internal event-time calculator — 2026-10-13

Full local PostgreSQL regression: **387 passed, one real-OCR skip, 60 warnings in 402.11 seconds**. The warnings include existing dependency/serialization and pytest temporary-directory cleanup warnings. Code commit `0740d48ba64dbf82bfbb0f1528e58617406222ef` passed [Linux CI](https://github.com/alisunkazemi21-cloud/Herman-SME-Financial-Advisor-Perisan/actions/runs/38317748850): **386 passed, two skipped, five warnings in 46.61 seconds**; Ruff and Marimo also passed. Counts differ for platform-specific checks.

The focused dated/legacy suite passed 46 tests (24 new dated cases). The first full run encountered a stopped/recovering local database: 213 passed, one skipped and 174 setup errors in 113.58 seconds. The existing test server was started, completed recovery without resetting data and passed readiness before the successful rerun. The full failure/recovery and scope record is in [the calculation run](../runs/dated-inventory-2026-10-13/README.md).

The independent eight-to-ten-unit example, activation boundary, backdated events, recipe input/output factors, incomplete timelines, unapproved candidates, dimension checks and unchanged legacy payloads pass. This does not verify database catalog revisions, source authority, migration, SKU alias conflict rules or freshness integration: no new public endpoint exists. C16 remains in progress and C15 is the last complete checkpoint. Graphify code-only extraction/report: 1,294 nodes, 4,133 edges, 71 communities; inferred coverage and unmeasured token savings remain explicit. The deferred notebook was checked, not expanded.

## C16 internal pack persistence and review — 2026-10-13

Full Windows PostgreSQL regression: **396 passed, one real-OCR skip, 63 warnings in 522.03 seconds**. Existing dependency/serialization and temporary-directory cleanup warnings remain; this does not validate real OCR quality. The focused PostgreSQL suite passed nine cases in 40.15 seconds. Implementation commit `9e21ef23e673d5a2273a5581b970153e6fcac564` passed [Linux CI](https://github.com/alisunkazemi21-cloud/Herman-SME-Financial-Advisor-Perisan/actions/runs/38362037530): **395 passed, two skipped, five warnings in 68.98 seconds**, followed by Ruff and Marimo checks. Platform-specific checks explain the count difference.

Migration 15, runtime RLS, immutable definitions/decisions, server timestamps, prospective order, competing approval uniqueness, source hash verification, history and timeline construction are exercised. An isolated database was built through migration 14 with a legacy conversion, upgraded and migrated again; its original factor and identity stayed unchanged, and no approval was fabricated. The migration test removes only its uniquely created test database.

[Run record](../runs/pack-catalog-2026-10-13/README.md), chapter, report and media narrative are synchronized. Graphify code-only extraction/report completed with 1,339 nodes, 4,286 edges and 75 communities; partial static coverage and unmeasured token savings remain explicit. Local Ruff passed; Marimo exited successfully with host configuration-access warnings. Product UI remains deferred.

No public catalog revision endpoints are exposed. Historical inventory bindings, item/SKU revisions, dated analysis selection, duplicate matching and freshness integration remain unfinished. C16 and the overall project goal remain active.

## C16 dated analysis, duplicate and freshness integration — 2026-10-13

Full Windows PostgreSQL regression: **398 passed, one real-OCR skip, 69 warnings in 488.74 seconds**. Existing dependency/serialization and temporary-cleanup warnings remain; no real OCR/model-quality claim follows. Code commit `16c4f3cb681ec88e9fa2181b81dfce9b6a1a1f43` passed [Linux CI](https://github.com/alisunkazemi21-cloud/Herman-SME-Financial-Advisor-Perisan/actions/runs/38363836437): **397 passed, two skipped, five warnings in 78.16 seconds**, with Ruff and Marimo successful. Counts differ for platform checks.

The related suite passed 42 cases; the final two-case integration rerun also covers historical case receipts and advisor pack-use suppression. Initial focused failures were a decimal-string formatting expectation and an outdated monkeypatch target after replacing the calculator; numerical comparison and the actual calculator hook preserve the intended assertions. The [run record](../runs/pack-integration-2026-10-13/README.md) records the independently expected 64-to-58 result, unchanged old receipt, legacy freshness interpretation and eight/ten-unit duplicate cases.

Migration 16 adds analysis pack-use receipts without changing saved input hashes. New analysis, freshness and duplicate matching consume reviewed dated definitions; public revision routes, historical inventory-row bindings and item/SKU lifecycle remain open. Ruff and whitespace checks passed; local Marimo exited successfully with host config-access warnings. Graphify refresh/report: 1,353 nodes, 4,370 edges and 86 communities, code-only, no measured token savings. Documentation artifacts are synchronized; product UI remains deferred.

The user's eight delivery risks are recorded in [PILOT_DELIVERY.md](PILOT_DELIVERY.md), with data readiness, reviewed action/outcome, real renewal and setup/recurring support effort as proposed acceptance measures. This is a planning contract, not implemented pilot telemetry or proven economics. External references in the brief are explicitly unverified research leads.

## C16 historical pack-binding storage — 2026-10-25

Code `f41c8fb`: final affected Windows PostgreSQL regression **68 passed, two warnings, 293.10 seconds**, including fresh pre-18 upgrade/reentry, preserved legacy receipt representations/hash, canonical paths, cutover barrier, resolution concurrency and source/role/tenant integrity. Readiness unit verification: **eight passed, one restricted-PostgreSQL case deselected, one warning, 4.55 seconds**; its separate local database rerun did not start because automatic permission review timed out twice. Ruff, whitespace and Marimo checks passed (existing Marimo user-config access warnings). Graphify code-only/report: 1,503 nodes, 4,843 edges, 88 communities; no measured token savings.

The test database initially was stopped and recovered before the final successful run; no reset was used. Shell publication and the connector fallback timed out in automatic permission review, while a sandbox push could not reach GitHub. Code is committed locally; full CI/publication remain pending, with no new remote result claimed. [Run evidence](../runs/pack-bindings-2026-10-25/README.md). Analysis/freshness/duplicate integration remains open. The [pricing dashboard contract](PRICING.md) is a designed extension, not tested implementation or proven pricing effectiveness.

## C16 shared pure pack interpreter — 2026-10-25

Local code `3b8e81d`: **99 related new/dated/legacy inventory tests passed in 1.97 seconds**. Independent review verified repairs to observation-before-review, receipt provenance/chronology, arithmetic/evidence guards, then the bounded nonnumeric capture trace. Ruff, whitespace and Marimo checks passed (existing user-config warnings). Graphify code-only/report: **1,565 nodes, 5,052 edges, 95 communities**. [Detailed evidence](../runs/pack-interpreter-2026-10-25/README.md).

The local PostgreSQL probe did not execute because automatic permission review timed out. No new SQL or full regression result is claimed. Analysis/freshness/duplicate integration remains open. The user subsequently authorized retrying database and GitHub work after ten minutes of connectivity recovery; an attempted heartbeat also timed out and was not saved. The active session tracks the retry rather than claiming a scheduled job exists.

## Authorized database reconnection and full local acceptance — 2026-10-25

The founder explicitly resumed commits, GitHub publication and database access. The existing PostgreSQL 17.11 cluster recovered and accepted connections after a direct sandbox `postgres.exe` startup. Two elevated startup requests timed out in automatic permission review before execution; the sandbox `pg_ctl` attempt failed with restricted-token error 87. No data reset or restore was performed. The temporary server is an active test process, not production supervision or a restore rehearsal.

The focused restricted-role readiness and binding regression passed **22 tests, one warning, in 57.84 seconds**. The full Windows PostgreSQL suite then passed **487 tests, one skipped real-OCR check, five warnings, in 748.65 seconds**. Application code is `3b8e81dad0530f056f953d5edb44e34e210996c8`; checkpoint HEAD when this full run began was `910faa0d9e6d36abb935836bd30a12e36a7569c2`. Only documentation changed during the run. This closes the previously pending local restricted-role readiness rerun and establishes the new full local regression result; it does not connect the unfinished consumers.

A read-only schema inspection found versions 1–18 and a missing `pack_binding_review_history` index in this existing development database: it had received migration 18 before that index was added to the still-unpublished migration. After the full suite, only that index was created concurrently, under bounded lock/statement settings, and its definition and valid flag were checked. No migration was replayed and no record/receipt changed. Readiness was rerun after alignment: **nine passed, one warning, in 5.07 seconds**. Fresh isolated migration-upgrade coverage is included in the full suite.

Ruff passed; Marimo check exited zero with existing host configuration-access warnings; the notebook is unchanged for this backend-only checkpoint. All **114 local Markdown links** in the synchronized checkpoint documents resolved. The pure suite was also rerun: **99 passed in 2.04 seconds**. Graphify code has not changed since the recorded 1,565-node refresh; no model extraction or measured token-saving claim is added.

The default Git push failed to connect to GitHub port 443. Both authorized elevated push attempts timed out in automatic permission review before execution. Read-only connector branch listing worked, but a commit read later failed with a transport error. **Publication and new Linux CI remain unverified**; preserve the local commits and ordinary fast-forward publication path. No branch, pull request or rebuilt mirror history was created. The next engineering task remains trusted bounded binding selection/capture and consistent analysis/freshness/duplicate integration. C16 and the overall application goal remain open.

[Run record](../runs/pack-interpreter-2026-10-25/README.md). No new live binding-consumer protection or production acceptance is claimed.

## C16 live binding consumers — October 26, 2026

Published code `33287366adc29c1e8483686b4070739f884f52ea`: full [Linux CI](https://github.com/alisunkazemi21-cloud/Herman-SME-Financial-Advisor-Perisan/actions/runs/40299373210) passed **513 tests, two skipped, 15 warnings, 89.96 seconds**, then Ruff/Marimo. The full Windows regression passed **514 tests, one real-OCR check skipped, five warnings, 862.56 seconds**, with exit code zero. New adapter/analysis/duplicate checks passed 17 in 45.45 seconds. The first joint run passed 52 but failed two negative tests because their parametrized value was shadowed by a fixture variable; the corrected freshness/analysis rerun passed 16 in 48.35 seconds, including separate resolution-only source tamper rollback. These scoped counts overlap and must not be summed.

An interrupted earlier handle was missing and supplies no result. The first resumed run found PostgreSQL stopped and returned two passes / 52 connection-setup errors in 48.63 seconds. Existing-cluster recovery then reported ready at October 26, 12:41:09 +03:30, without reset/restore/replayed migration. Ordinary Git pushes now succeeded under renewed user authorization; the prior checkpoint `4b2fd57` also passed CI.

Review repairs cover metadata query limits under explicit `max_rows=None` and final encoded duplicate-envelope bytes. Reviewers executed no tests; the lead implemented and validated all changes. Graphify code-only/report: 1,637 nodes, 5,341 edges, 86 communities. Local Ruff/whitespace passed; Marimo exited zero with existing host config-access warnings and the notebook unchanged. [Synchronized run evidence](../runs/binding-consumers-2026-10-25/README.md). Current labels/public workflows and broader production/pilot gates remain open.

## C16 complete public catalog workflow — October 26, 2026

Accepted compatible-edit backend scope at code `f877b9b0ee782caec53bfa3792e7453e94af187f`: full Windows PostgreSQL regression **544 passed / one real-OCR skip / five warnings / 777.37 seconds**, exit zero. Exact-code [Linux CI](https://github.com/alisunkazemi21-cloud/Herman-SME-Financial-Advisor-Perisan/actions/runs/40307392553), job `121519765097`, passed **543 / two skips / 15 warnings / 105.34 seconds**, followed by Ruff/Marimo. Only documentation changed during the local full run.

Lead final-scope acceptance passed 51 tests in 140.84 seconds; final detail/alias/backdating cases passed four in 8.52 seconds. Worker new-label and HTTP suites passed 15 and 11 respectively; their initial fixture-time/role/key mistakes were repaired before clean runs, then included in the lead's final/full checks. Counts overlap. Independent review's missing historical-use distinction was repaired on standalone pack detail/history and closure confirmed. The pure scoped ASGI header wrapper passed readiness/cancellation and full parser regression.

[Requirement-by-requirement acceptance mapping](../runs/catalog-workflow-2026-10-26/README.md#acceptance-mapping), [API guide](CATALOG_API.md), chapter, reports/media, README and progress map are synchronized; the notebook is unchanged with a successful check and existing host config-access warnings. Graphify code-only/report: **1,751 nodes, 5,778 edges, 113 communities**; graph artifacts remain local and token savings unmeasured. No new migration, restore, production deployment, real-model/OCR evaluation, complete workload test or pilot outcome was claimed. The full original application goal remains active.
## C17 completeness/actions — accepted backend scope

Published implementation `c585774575c0bce7fcb3fe5171fab0e1ea831069` adds migrations 19–20, mandatory reviewed completeness for managed analyses, preserved original declarations/receipts, provisional/legacy current-figure suppression and immutable responsible-person action history. Final isolated coverage component: **13 passed in 144.35 seconds**, including a newly imported unanalysed 10,001-row tenant under a ten-second SQL limit. Lead action/API/metadata/timeout scope: **33 passed, one warning, 209.53 seconds**. Import-provenance/readiness scope: **10 passed, one warning, 21.94 seconds**. Counts overlap.

The first full development run finished **563 passed / 13 failed / one real-OCR skip / 1719.85 seconds** before fixture/expectation repairs and query fencing. It exposed a stale-statistics quadratic details/header rescan; the known CPU-active test query was cancelled deliberately. A rollback-only reproduction exceeded fifteen seconds on the old plan and completed in 1.863 seconds after exact primary-key lookup fences. Added savepoint-protected SQL budgets preserve stricter caller limits and recover timeout failures before subsequent context reads. At that development stage, the full regression and [initial CI](https://github.com/alisunkazemi21-cloud/Herman-SME-Financial-Advisor-Perisan/actions/runs/40355665508) had not completed; final acceptance is recorded below.

Fresh isolated databases migrated from template0 through version 20. The earlier development database was aligned by replacing only the three still-unreleased completeness functions and adding its missing finite-period check; workflow/analysis row counts were unchanged. No source records, receipts or history were rewritten. Ruff and whitespace checks passed; Marimo exited zero with existing host configuration-access warnings, and its notebook is unchanged. Local code-only Graphify refresh/report: **1,931 nodes, 6,422 edges, 121 communities**; no semantic/model extraction or measured token-saving claim.

[Detailed run](../runs/completeness-actions-2026-10-26/README.md) records component ownership, independent review, earlier mixed-version failure and acceptance gates. C17 was not accepted at that intermediate stage. Final backend acceptance is recorded below; the broad application, real-engine, recovery, capacity, UI and pilot gates remain open.

First C17 Linux CI at `c585774`: **588 passed, one failed, two skipped, 15 warnings, 158.29 seconds**. The lone failure compared timestamp strings in the new HTTP test: UTC and Tehran representations denoted the same instants. The test now compares typed complete proposals and explicitly runs under both PostgreSQL UTC and Asia/Tehran sessions; **two local cases passed in 20.37 seconds**. Application code is unchanged. The local full run was still live at that point; the final result and successful test-only CI follow-up are recorded below.

Final C17 acceptance: the Windows full run ended successfully with **590 passed, one real-OCR skip, five warnings, 1133.34 seconds**, exit zero. It started at implementation `c585774`; application sources remained unchanged through test-only follow-up `9611c11`. The additional UTC/Tehran parameter case was validated separately locally, then included in [final Linux CI](https://github.com/alisunkazemi21-cloud/Herman-SME-Financial-Advisor-Perisan/actions/runs/40357187856), job `121692701606`: **590 passed, two skipped, 15 warnings, 148.72 seconds**, plus Ruff and Marimo. Collection/platform skips differ as explained in the run. The aligned earlier development database also passed all nine readiness checks in 10.08 seconds. Final code-only Graphify/report: **1,931 nodes, 6,422 edges, 121 communities**. The checkpoint is accepted within its documented backend bounds; all broader open gates remain open.
