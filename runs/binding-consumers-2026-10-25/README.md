# C16 historical binding consumer integration

Started October 25; resumed October 26, 2026 after interruption. Code: `33287366adc29c1e8483686b4070739f884f52ea`. **Live consumer behavior is implemented and full Linux/Windows regressions passed. C16 remains open for current labels and public reviewed catalog workflows.**

## Delivered behavior

`select_binding_state` reads typed observations, stable legacy flags, full source/ingredient/fulfillment/recipe-path checks and approved resolutions in the caller's scoped snapshot, then captures server as-of time. Analysis and freshness share the 10,000-row selection budget, including metadata. New `pack_bindings` snapshots declare `inventory.pack_bindings.v1`, and final encoded input/comparison envelopes are capped at 8 MiB. The explicit helper option `max_rows=None` retains its older base-selection behavior, while binding metadata still uses independently limited queries. Normal application consumers pass finite budgets.

Analysis uses pure preflight, authorized source-key batch capture, bounded reload and final calculation. A context becoming past without a persisted check rejects the attempt for retry. Final check/review identities are included before hashing; original, definition and resolution-only source bytes are verified before storing results. SQL derives capture meaning; capture cannot approve an unsupported factor. Capture, analysis, audit and idempotency remain one transaction.

Freshness compares stable metadata and approved decisions while ignoring as-of clock passage alone. A new approved resolution makes earlier current context stale; a rejected one does not change numeric selection. Legacy pack snapshots missing binding context return explicit unknown, with a Persian review/reanalysis explanation. Compatible legacy no-pack comparisons remain available. Reads do not calculate a replacement, capture checks or rewrite earlier receipts.

Duplicate comparison resolves each source's own direct context and skips a numeric match if either result is unavailable, including both unavailable. Existing document/event/warehouse/kind/lineage rules remain. Candidate, definition and metadata row/read-byte budgets fail explicitly; an additional final-envelope byte check covers representation overhead after review evidence is nested. Budget failure rolls back approval instead of accepting a partial no-match.

## Validation evidence

- Pure new/dated/legacy inventory suite after explicit state version: **99 passed in 2.00 seconds**.
- Initial adapter SQL suite: **six passed, one warning, 22.26 seconds**.
- New adapter/analysis/duplicate suite after review fixes: **17 passed, one warning, 45.45 seconds**. This includes the bounded `max_rows=None` callback regression, per-record late-baseline/unavailable comparisons, final byte-envelope boundary and approval rollback.
- First joint run after recovery: **52 passed, two failed, five warnings, 172.39 seconds**. The two failures were new negative-test fixture variable shadowing: a local `AnalysisInput` replaced the parametrized invalid value. The tests were repaired.
- Final focused freshness/analysis rerun: **16 passed, one warning, 48.35 seconds**. The review-source tamper test now uses a separate resolution-only document, distinct from coverage/policy, source and definition evidence; a failed analysis rolls back the newly captured recipe check.
- Code-commit [Linux CI](https://github.com/alisunkazemi21-cloud/Herman-SME-Financial-Advisor-Perisan/actions/runs/40299373210), job `121493193009`: **513 passed, two skipped, 15 warnings, 89.96 seconds**, followed by successful Ruff and Marimo. This is the exact code revision above.
- Full local Windows regression: **514 passed, one skipped real-OCR check, five warnings, 862.56 seconds**. The process exited zero; application source matched `3328736` throughout, with documentation-only changes during the run.

Independent expected examples retain the future revision's **64-to-58** shortage change and exact 18-unit usage, while a reviewed recipe uses **0.25 pack × 8 = 2 units** and yields zero unexplained shortage for opening eight/closing six. Tests retain prior analysis/case receipts, record check/review IDs before hashing, distinguish legacy unknown, exercise a deterministic simultaneous capture race, and simulate the future-to-past guard without changing the system clock. The latter is injected boundary coverage, not an elapsed-time acceptance claim.

## Review and actual ownership

Three implementation assignments were dispatched with separate ownership; no edits were delivered before the lead consolidated implementation. The lead wrote all source and tests. Specialists then performed read-only reviews. The database reviewer read the installed Database Reliability Engineer brief and found that the `max_rows=None` callback could fetch metadata without a SQL limit. The lead repaired it and added a real-query limit assertion. The duplicate reviewer found uncharged final-envelope overhead; the lead added the final cap and a real PostgreSQL boundary test. That reviewer confirmed source closure. The analysis reviewer found no actionable issue in capture/reload, chronology, bounds, IDs/hash, resolution evidence or rollback. No reviewer executed tests. The lead also read the installed Backend Architect brief, retaining the modular backend and existing transaction/RLS controls rather than adopting unrelated template examples or unmeasured performance targets.

## Interruption, server and publishing

An earlier joint process handle was missing after interruption; it contributes no passing evidence. The first resumed attempt found PostgreSQL stopped and ended with **two passed / 52 connection-setup errors / 48.63 seconds**. Direct startup recovered the existing PostgreSQL 17.11 cluster; its log reported ready at **October 26, 12:41:09 +03:30**, and `pg_isready` accepted connections. No data reset, restore or migration replay was performed. The active test process is not production supervision or a recoverability drill.

The user reported stable connectivity and authorized GitHub Desktop/web publication. Computer Use inventory did not return GitHub Desktop; the later web authorization allowed ordinary Git publication. `919bcb7..4b2fd57` and then `4b2fd57..3328736` were pushed normally to `main`; no history was rebuilt or force-pushed. The [previous checkpoint CI](https://github.com/alisunkazemi21-cloud/Herman-SME-Financial-Advisor-Perisan/actions/runs/40297341126) also passed. No scheduled background job or PR was created.

## Synchronized artifacts and remaining gates

Ruff and whitespace checks passed. Marimo exited zero with existing host config-access warnings; the notebook is unchanged because this checkpoint changes backend behavior. Graphify code-only extraction/report completed with **1,637 nodes, 5,341 edges and 86 communities**; no semantic/model extraction or measured token-saving claim. Generated graph artifacts remain local. All **122 local Markdown links** in the synchronized checkpoint documents resolved. The chapter, technical report, media narrative, README and progress map track the same code and observed results.

Next: current item-label presentation and reviewed public catalog/binding workflow, then completeness/action records under the forty-day plan. Public revision routes remain gated. Real OCR/local-model quality, coordinated database/blob restore, a complete 1,000-business workload and permissioned pilot/recurring-value evidence remain open. No full application or production-readiness claim follows.
