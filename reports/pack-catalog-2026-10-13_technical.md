# C16 pack revision persistence — 2026-10-13

Status: internal persistence and review slice; complete C16 and public catalog workflow remain open.

## What changed

Migration 15 captures existing conversion rows as immutable baseline definitions without fabricated historical authors or approvals. Each new factor revision references an eligible predecessor and keeps factor/source in one sealed row. Separate reviewer decisions have server-stamped times and prospective activation. At most one approved successor can occupy a predecessor slot; rejection does not consume it. A later future revision must activate strictly after its predecessor.

The internal Catalog service uses existing audit/idempotency transactions, checks source bytes at proposal and approval, offers paginated history and constructs half-open timelines from approved successor decisions. Database RLS enforces tenant, author and reviewer identity. Runtime has no update/delete grants; append-only triggers also reject privileged accidental changes. These controls do not protect against a malicious database administrator changing schema or disabling triggers.

## Evidence

Focused PostgreSQL suite: **9 passed in 40.15 seconds**, 58 warnings (primarily inherited pytest temporary cleanup and dependency warnings). Earlier eight-case run passed before adding the isolated upgrade case. Tests cover baseline capture, migration reentry, migration from versions 1–14 in a uniquely named disposable database, exact legacy conversion preservation, idempotency/audit, source tampering, rejected candidates, competing approvals, stale predecessors, backdating/future ordering, forbidden author/reviewer actions, tenant visibility and immutable rows.

Full Windows PostgreSQL regression: **396 passed, one real-OCR skip, 63 warnings in 522.03 seconds**. Existing dependency/serialization and temporary-directory cleanup warnings remain; this does not validate real OCR quality.

Implementation commit `9e21ef23e673d5a2273a5581b970153e6fcac564` passed [Linux CI](https://github.com/alisunkazemi21-cloud/Herman-SME-Financial-Advisor-Perisan/actions/runs/38362037530): **395 passed, two skipped, five warnings in 68.98 seconds**. Ruff and Marimo passed.

Graphify code-only refresh: 1,339 nodes, 4,286 edges, 75 communities. Semantic inference and token savings were not measured. Ruff passed; local Marimo check exited successfully with host configuration-access warnings. The deferred notebook remains unchanged.

## Remaining integration

This internal service has no public routes. Existing business analysis, duplicate normalization and freshness still use the legacy conversion contract; they must move together to the dated timeline before a public revision workflow is enabled. Migration 15 captures definition baselines but does not bind historical inventory rows. Item name/SKU lifecycle, historical binding migration, source lineage integration, analysis/case immutability acceptance and public endpoint tests remain C16 gates. C15 is still the last fully verified checkpoint. Real engine quality, production workload/recovery and owner UI remain separate unfinished requirements.
