# Journal report integration technical report

Migrations 010 and 011 add mapping/report proposals and reviewer decisions, immutable JSON manifests/results, tenant keys and a unique approved-replacement constraint. Report creation reads approved journal inputs in one repeatable snapshot and verifies source files. Canonical input/result hashes accompany source-line provenance. Reports are bounded and fail without partial publication.

The portfolio selects reviewed statement snapshots and active reviewed journal reports together. Competing latest-period sources return conflict. Freshness compares source entry IDs; stale and superseded reports return no numeric advisor/portfolio values. Full historical receipts remain available. The new optional advisor selector preserves old case request serialization when omitted, avoiding an idempotency break during upgrade.

The 39-test focused suite passed, including 11 new report tests. Full-suite, static checks and graph refresh evidence appear in [validation](../research/VALIDATION.md). All financial data were synthetic and model responses stubbed. The management cash summary uses net cash per journal; gross bank-flow classification, closing-period controls, statutory statements and larger batch reports remain incomplete. UI work remains deferred.
