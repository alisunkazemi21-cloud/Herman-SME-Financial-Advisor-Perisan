# Herman specialist delivery team

Inspected 2026-10-24 at the founder's explicit request. The workspace parent `.codex/agents` contains 282 parseable TOML definitions, each with developer instructions: 65 engineering, 12 security, 9 testing, 10 design, plus other disciplines. This inventory validates file structure, not every instruction or claimed capability. These are role briefs; no new executable tools, credentials or external services were installed.

## Operating model

The lead integrates the existing codebase, assigns bounded work and owns release decisions. Use up to three concurrent specialists only for independent tasks. Each writer owns named files and must preserve other work. Read-only reviewers report paths and reproducible findings. A completed agent response is not a passed acceptance gate. Verify implementation with appropriate tests and review before committing; preserve the existing checkpoint evidence and immutable-data contracts.

Some installed definitions are not selectable named roles in this session. In that case use an available worker/explorer role, explicitly instruct it to read the relevant local definition, and report that adaptation accurately. Do not change model settings or install dependencies merely because a role template mentions them. Specialist templates do not override the user's scope, project instructions or tool permissions.

| Responsibility | Installed briefs | Assignment / gate |
|---|---|---|
| Delivery coordination | Agents Orchestrator; Project Shepherd | Dated scope, dependencies, founder tasks and evidence links; no invented progress percentage or delivery guarantee. |
| Backend and data integrity | Backend Architect; Database Reliability Engineer | C16 lifecycle, restricted runtime, migrations, recovery and bounded failures. Prefer the existing modular backend. |
| Pilot workflow | UX Researcher; Project Shepherd | Owner/operator routine, missing-data states, manual reference and observed assistance/time. |
| Implementation | Relevant engineering brief through a worker | One independently reviewable slice with explicit file ownership. |
| Independent verification | API Tester; Test Automation Engineer; Reality Checker | Test actual behavior and failure cases. UI screenshots apply when a UI exists; they cannot prove database correctness. |
| Later owner interface | UX Architect; UI Designer; UI Finish-Gate Reviewer | Minimal Persian/RTL workflow after backend gates; Kalameh preference and existing fallback. |

## Work actually performed in this checkpoint

- Backend release explorer read the Backend Architect and Database Reliability Engineer briefs, queried Graphify and checked source/tests. No tests were run by this reviewer.
- UX Researcher reviewed the pilot contract and delivered a first-week data-readiness checklist and four-period observation schedule.
- Delivery worker read Project Shepherd and Agents Orchestrator and authored the forty-day plan.
- Lead parsed the inventory, reconciled findings and updated project priorities. No additional agents or tools were installed.

## Concrete audit findings and next implementation

The existing `/health` route is process liveness only. Add separate bounded readiness for database access/schema compatibility and usable evidence storage, with sanitized failures and tests for post-startup outages. Delivered October 25: the readiness slice passed 407 Windows tests / one skip and 406 Linux tests / two skips, with independent cancellation review. See [the evidence](../runs/readiness-2026-10-25/README.md). It does not open C16 catalog routes early. The next primary engineering task returns to C16 historical bindings and item/SKU lifecycle.

Other open release gates: operator credential renewal (provisioned credentials expire after 30 days), deployment supervision/TLS, database-plus-blob coordinated backup and isolated restore, real OCR/model evaluation, and representative concurrent workload testing. Existing backend CLI supports migration, provisioning, serving and workers; `tests/test_cli.py` tests the separate analysis CLI, not operator bootstrap. See `src/backend/cli.py`, `database.py`, `api.py`, `service.py`, `jobs.py`, `worker.py` and `tests/test_backend.py`, `tests/test_document_jobs.py`.

The capacity target remains at least 1,000 business identities. Existing synthetic reads do not establish complete ingestion/worker/reporting capacity. Role descriptions claiming scale or speed are not benchmark evidence.

## October 25 follow-up assignments

Historical pack storage received independent review of canonical recipe paths, approved-successor provenance and cutover locking; all three findings were repaired and included in the lead's final 68-test affected PostgreSQL run. The lead then added receipt-preservation checks, schema-readiness probes and synchronized artifacts.

A separate read-only pricing-contract assignment was dispatched using the installed Backend Architect brief as the requested role reference. It returned a design checklist but explicitly reported that no files were read or verified before interruption. Treat it as unverified suggestions, not independent approval of the pricing contract or evidence that the role brief was applied. The lead owns the current contract, primary-source review and integration decisions. No pricing implementation or new executable tool was installed by that assignment.

The later bounded Backend Architect review inspected the named analysis/selection/freshness/duplicate files after Graphify consultation and returned concrete integration findings. It then reviewed the new pure interpreter and tests, identified missing observation/review chronology and contradictory receipt provenance, verified the repairs, and checked the bounded encountered-context trace. No files were changed or tests executed by that reviewer. The lead implemented and ran the final 99-test related suite. This is source-review evidence for that component, not SQL or full-application acceptance.

## October 26 live-consumer review

Three disjoint implementation assignments were dispatched, but no code was delivered before ownership returned to the lead. The lead implemented all adapter, consumer and test changes. The children were reused for read-only review: the Database Reliability Engineer brief reviewer found an unbounded metadata callback when the base selection limit was disabled; the duplicate reviewer found uncharged final-envelope overhead and subsequently confirmed the source repair; the analysis reviewer found no actionable issue in the scoped capture/reload, limits, IDs/hash, chronology, evidence or atomic rollback. The lead repaired both budget issues and ran their regressions. No reviewer edited files or executed tests. The lead also consulted the installed Backend Architect brief and retained the existing modular/RLS/transaction design.

Exact-code Linux CI passed 513 tests / two skips; full Windows regression passed 514 tests / one real-OCR skip in 862.56 seconds. These reviews support the named integration, not accounting expertise, measured capacity, OCR/model quality or a finished public catalog workflow. [Evidence and ownership](../runs/binding-consumers-2026-10-25/README.md#review-and-actual-ownership).

## October 26 C16 workflow completion

The lead owned catalog service/public routes, pure ASGI headers, manual capture conflict handling, extra acceptance cases and release evidence. One worker owned only dated label models/selection, analysis/freshness integration and its new test module; a second owned only the new HTTP acceptance test file. The assignments referenced the installed Backend Architect and API Tester briefs, with bounded tasks and no model/tool installation. Both delivered within ownership; the lead preserved their edits and ran integration/full checks.

The dated-label worker then reviewed lead-owned API/catalog/capture code read-only, found a missing historical-use distinction on standalone pack detail, and confirmed the repair on detail/history plus the ASGI forwarding behavior. Its review phase executed no tests; its earlier implementation-phase tests are recorded separately. The lead reviewed the worker's identity/time/source/budget logic. The HTTP worker's passing acceptance cases include public concurrency, old case/import/analysis preservation and isolated label-source tamper rollback.

Lead joint/final scoped runs passed 51 and four cases; full Windows passed 544 / one skip, and exact-code Linux CI passed 543 / two skips. [Actual ownership, initial fixture failures and acceptance evidence](../runs/catalog-workflow-2026-10-26/README.md). C16 is accepted within this backend scope; this does not certify financial expertise, real-engine quality, customer usability or production capacity.
## October 26 C17 ownership and review

The lead recorded the completeness/action contract and owns managed-analysis selection, derivation, freshness, advisor/portfolio gating, public routes, migration/grant/readiness wiring, fixture migration and release artifacts. A worker using the Database Reliability Engineer brief owns only migration 19, coverage models/selection/workflow and its component tests. Another using the Backend Architect brief owns only migration 20, action service and component tests. The earlier binding-adapter chat was reused for a fresh bounded API Tester assignment owning only the C17 HTTP test file. No model, dependency or external service was installed.

The action worker's read-only integration review found that portfolio previews bypassed provisional gating; the lead repaired that consumer and the API worker added context/overview/portfolio assertions. The coverage worker independently reviewed the action SQL/service/public route connections read-only and found no actionable issue. These review phases ran no tests. The coverage worker also reproduced the unanalysed-tenant quadratic plan in a rollback-only transaction and verified the fenced lookup repair; the lead added SQL budgets/recovery and cross-timezone assertions. Final full acceptance: 590 Windows passes / one skip, 590 Linux passes / two skips. Component runs and failed development checks remain in the [C17 run](../runs/completeness-actions-2026-10-26/README.md).
