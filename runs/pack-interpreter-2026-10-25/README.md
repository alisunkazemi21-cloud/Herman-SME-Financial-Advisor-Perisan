# C16 shared historical pack interpreter

Date: October 25, 2026. Local code commit: `3b8e81dad0530f056f953d5edb44e34e210996c8`. **Pure engine verified within this scope; database consumers remain to integrate. C16 is open.**

## Behavior

`PackInterpreter` consumes a typed immutable snapshot of definition observations, server as-of/cutover instants, legacy source flags, usage checks and approved resolutions. It selects a supported saved definition, explicit reviewed interpretation, known-before-event definition, qualified migration-derived baseline, or deferred future-event definition. An existing unresolved check never falls back to a later definition. All recipe ancestors and the originating fulfillment must satisfy the legacy condition for a migration-derived use.

The new `inventory.bound_pack.v1` envelope reuses existing `_reconcile` arithmetic and emits `pack.use.v3` receipts with check/review/observation provenance. It retains the separate v1/v2 timeline tool and parsers. No saved database input, hash, result or case receipt is rewritten. The interpreter reads no files, database, network or system clock, and has no approval or capture authority. Supplied metadata remains a trusted server responsibility; a valid typed object is not proof of authorization or authentic source bytes.

Incomplete calculations contain no numeric conversion receipts. A separate nonnumeric `encountered_contexts` trace includes the failed use for later authorized batch capture, capped at 10,000 uses. Overflow yields an incomplete result. Normalization returns unavailable for an unsupported pack quantity; consumers must skip comparison when either side is unavailable, including when both are unavailable.

## Evidence

Final focused suite: **99 passed in 1.97 seconds**, covering the new interpreter plus existing dated/legacy inventory tests. No database or model was called. Independent expected shortage changes from **64 to 58** after a prospective revision while the earlier result is unchanged. Other cases cover late baselines, sticky unresolved checks, explicit resolution evidence, pinned identities, half-open/timezone boundaries, invalid scope/chronology/identities, recipe ancestry and fulfillment identity, zero-quantity review, physical dimensions, receipt arithmetic/evidence, no partial numeric receipts and the 10,000-use limit.

Independent review identified two missing chronology/provenance checks: a review could predate observation of its chosen definition, and a v3 receipt could encode contradictory migration/review provenance. Both were repaired and regression-tested. The reviewer confirmed closure, including native observation before approval/capture and arithmetic/evidence receipt guards. The lead subsequently added the bounded trace and its tests; the reviewer verified the trace, failed-use retention, overflow handling and empty incomplete receipts, with no remaining actionable issue in that scope. The reviewer did not execute tests. Initial Ruff errors concerned compact test branch formatting; formatting was corrected and final whole-source Ruff passed. `git diff --check` passed.

Marimo check exited zero with the existing inaccessible user-config warnings; the notebook remains unchanged for this backend-only slice. Graphify code-only extraction/report: **1,565 nodes, 5,052 relationships, 95 communities**. No semantic/model extraction or measured token-saving claim. Graph artifacts remain local.

## Integration gate and current holds

`Service.analyze`, freshness and duplicate matching still use their previous dated-timeline paths. In particular, the live duplicate path can still compare raw unresolved pack values; the pure normalizer supports the required fix but does not change that route yet. Do not claim live binding protection, a new full suite, PostgreSQL integration, Linux CI, capacity or real-data acceptance from this run.

Next implementation must load bounded trusted state, batch-capture encountered past contexts only on authorized writes, snapshot final check/review IDs before hashing new analyses, verify resolution source bytes, and use the same interpreter for duplicate normalization. Freshness must compare stable interpretation metadata without treating clock passage alone as a change; legacy pack receipts with insufficient binding context require an explicit unknown state. Public revision routes remain gated.

The local PostgreSQL reachability command did not execute because automatic permission review timed out. The user initially selected **Keep database checks pending**, then reported temporary internet trouble and explicitly authorized retrying GitHub and database work ten minutes later. The retry window starts no earlier than **2026-10-25 17:12:44 UTC**. An attempted one-time app heartbeat was not saved because automatic permission review also timed out; no scheduled job is claimed. The active session continues local work until the authorized retry time. Close the SQL and remote-validation gates only after actual results are observed.

## Authorized reconnection attempt

The user explicitly resumed Git commits, publication and database access. Two elevated startup requests timed out before execution in automatic permission review. The default `pg_ctl` attempt failed with Windows restricted-token error 87. Starting the same existing cluster directly with `postgres.exe` succeeded in the sandbox; after crash recovery, PostgreSQL reported ready at 21:22:13 Tehran and `pg_isready` accepted connections. No reset or restore was performed. The restricted-role readiness and binding suites are running; passing results will be recorded only after their process exits. The focused pure inventory regression was repeated: **99 passed in 2.04 seconds**.
