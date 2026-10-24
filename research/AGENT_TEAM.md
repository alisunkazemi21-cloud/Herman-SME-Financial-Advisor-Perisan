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

The existing `/health` route is process liveness only. Add separate bounded readiness for database access/schema compatibility and usable evidence storage, with sanitized failures and tests for post-startup outages. This is the next independent reliability slice; it does not open C16 catalog routes early.

Other open release gates: operator credential renewal (provisioned credentials expire after 30 days), deployment supervision/TLS, database-plus-blob coordinated backup and isolated restore, real OCR/model evaluation, and representative concurrent workload testing. Existing backend CLI supports migration, provisioning, serving and workers; `tests/test_cli.py` tests the separate analysis CLI, not operator bootstrap. See `src/backend/cli.py`, `database.py`, `api.py`, `service.py`, `jobs.py`, `worker.py` and `tests/test_backend.py`, `tests/test_document_jobs.py`.

The capacity target remains at least 1,000 business identities. Existing synthetic reads do not establish complete ingestion/worker/reporting capacity. Role descriptions claiming scale or speed are not benchmark evidence.
