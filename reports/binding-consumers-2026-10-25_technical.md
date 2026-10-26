# Historical binding consumers: technical report

Code `33287366adc29c1e8483686b4070739f884f52ea` connects typed historical package interpretation to analysis, freshness and duplicate matching. Trusted metadata shares selection row limits; final analysis/comparison envelopes are limited to 8 MiB. Explicit state versions and persisted check/review identities precede input hashing. Captures remain SQL-derived, source-key-specific, write-only and atomic with analysis/audit/idempotency.

Resolution-only evidence bytes are checked separately from other source roles. Current-context freshness excludes clock-only changes, includes approved resolutions and marks unsupported legacy package context unknown. Numeric duplicate candidates require supported independent normalization of both sides. Budget failures block approval rather than returning a partial no-match.

New adapter/analysis/duplicate tests passed 17 cases; repaired freshness/analysis tests passed 16. Review fixes cover bounded metadata SQL when the helper base limit is disabled and the actual final encoded envelope. Exact-code Linux CI passed **513 tests, two skipped, 15 warnings, 89.96 seconds**, plus Ruff/Marimo. Full Windows regression passed **514 tests / one real-OCR skip / five warnings / 862.56 seconds**. Graphify: 1,637 nodes / 5,341 edges / 86 communities, code-only. [Run evidence](../runs/binding-consumers-2026-10-25/README.md) records failed attempts, repairs, server recovery, exact revisions and reviewer scope.

The database is locally reachable and source commits are published. This does not validate production supervision/restore, actual model/OCR quality, a complete 1,000-business workload, pilot outcomes or the still-gated public catalog workflow.
