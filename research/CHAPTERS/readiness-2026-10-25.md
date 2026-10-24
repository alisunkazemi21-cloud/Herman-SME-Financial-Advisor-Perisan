# Dependency readiness checkpoint

Date: 2026-10-25. Independent reliability slice under M40-1; C16 remains in progress.

The backend now exposes `/ready` alongside process liveness at `/health`. Readiness performs restricted zero-row SELECTs for pack receipt/catalog features and a unique temporary write, flush, fsync, read and delete in the evidence root. No tenant records are fetched and no customer blobs are changed. Failure returns generic HTTP 503/unavailable with no-store; healthy returns HTTP 200/ready. The operator must provision the root; a missing directory is not recreated.

Database connections use a two-second connection timeout, two-second statement timeout, half-second lock timeout and read-only transactions. These are individual database budgets, not a strict overall deadline for multihost connections or operating-system/filesystem stalls. Per-process single-flight admission rejects busy checks. The probe worker releases admission only when its work finishes; the shielded, retained task survives HTTP request cancellation.

## Validation and review

Initial unit checks passed seven tests with one PostgreSQL skip. Independent API/DB reliability review reproduced overlapping probes after request cancellation. The repair moved slot release into the worker and added a cancellation regression. The reviewer found no remaining actionable issue in the scoped repair. The final readiness/backend suite passed **15 tests**, two warnings, **25.75 seconds**, including nine readiness cases with real restricted PostgreSQL access. Database-outage responses are tested by injected driver failure after a successful real probe; this does not claim a live server shutdown drill.

The first elevated integration attempt failed during pytest temporary-directory setup (Windows access denied), before those affected checks ran. Retrying in a fresh workspace basetemp resolved the environment failure. Ruff passed. Marimo check exited successfully with existing host config-access warnings; the notebook is unchanged.

Code commit: `62713f139ec0831c9950e6799656deca9fec27f9`. [Linux CI](https://github.com/alisunkazemi21-cloud/Herman-SME-Financial-Advisor-Perisan/actions/runs/40141679259) passed **406 tests, two skips, 15 warnings in 59.23 seconds**, followed by Ruff and Marimo. Full Windows PostgreSQL regression passed **407 tests, one real-OCR skip, six warnings in 548.87 seconds**. Graphify code-only extraction and report regeneration completed: **1,376 nodes, 4,427 relationships, 86 communities**. No model extraction was used; token savings remain unmeasured. This closes the documented readiness slice; wider release gates remain open.

## Limits and next work

This checks selected schema features and root I/O, not every permission/schema object, source integrity, queue/model health, recovery or capacity. No migration or additional DB privilege is introduced. It does not close C16 historical bindings/item aliases/public routes. Next engineering returns to that lifecycle; credential renewal, coordinated database/blob restore, deployment supervision/TLS and real document/model/workload validation remain release gates.
